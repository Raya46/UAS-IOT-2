import os
import yaml
import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from ai.utils.config import Config
from ai.utils.geometry import point_inside_polygon


class ZoneManager:
    def __init__(self, config: Config, yaml_path: str = "ai/zones.yaml"):
        self.yaml_path = yaml_path
        self.config = config
        self.zones: List[Dict[str, Any]] = []
        self.load_zones()
        self.traffic_light_frames = 0
        self.u_turn_sign_frames = 0
        self.lane_model = None
        self.yolop_model = None
        self.frame_count = 0
        self.cctv_lanes_fitted = False
        self.default_zones = list(self.zones)
        self.current_source_label = None
        self.density_map = None

    def update_detection_states(
        self, has_traffic_light: bool, has_u_turn_sign: bool
    ) -> None:
        """Updates frame countdowns for detected traffic signs and lights to prevent flickering."""
        if has_traffic_light:
            self.traffic_light_frames = 60  # Keep active for ~2 seconds at 30 FPS
        elif self.traffic_light_frames > 0:
            self.traffic_light_frames -= 1

        if has_u_turn_sign:
            self.u_turn_sign_frames = 60  # Keep active for ~2 seconds at 30 FPS
        elif self.u_turn_sign_frames > 0:
            self.u_turn_sign_frames -= 1

    def load_zones(self) -> None:
        """Loads zones from zones.yaml. If it does not exist, loads fallback from config.yaml."""
        if os.path.exists(self.yaml_path):
            try:
                with open(self.yaml_path, "r", encoding="utf-8") as file:
                    data = yaml.safe_load(file) or {}
                    self.zones = data.get("zones", [])
                print(f"[INFO] Loaded {len(self.zones)} zones from {self.yaml_path}")
                return
            except Exception as exc:
                print(
                    f"[WARN] Failed to load zones from {self.yaml_path}: {exc}. Using config fallback."
                )

        # Fallback to config.yaml default polygon
        default_poly = self.config.get("zone.no_parking_polygon", [])
        if default_poly:
            self.zones = [
                {
                    "id": "zone_default",
                    "name": "No Parking Zone (Config Fallback)",
                    "type": "no_parking",
                    "enabled": True,
                    "points": default_poly,
                    "rule_config": {
                        "min_seconds": float(
                            self.config.get("violation.illegal_parking_seconds", 5)
                        )
                    },
                }
            ]
            print(f"[INFO] Initialized with 1 default zone from config.yaml")
        else:
            self.zones = []
            print(f"[WARN] No zones configured. Map is empty.")

    def save_zones(self) -> None:
        """Saves current zones list to zones.yaml."""
        try:
            os.makedirs(os.path.dirname(self.yaml_path) or ".", exist_ok=True)
            with open(self.yaml_path, "w", encoding="utf-8") as file:
                yaml.safe_dump({"zones": self.zones}, file)
            print(f"[INFO] Saved {len(self.zones)} zones to {self.yaml_path}")
        except Exception as exc:
            print(f"[WARN] Failed to save zones to {self.yaml_path}: {exc}")

    def get_zones_by_type(self, zone_type: str) -> List[Dict[str, Any]]:
        return [
            zone
            for zone in self.zones
            if zone.get("type") == zone_type and zone.get("enabled", True)
        ]

    def get_zone_colors(self, zone_type: str) -> Tuple[int, int, int]:
        """Returns premium BGR colors for transparent overlays based on zone type."""
        colors = {
            "no_parking": (0, 0, 255),  # Red
            "shoulder_lane": (0, 165, 255),  # Orange
            "red_light_stop_line": (255, 0, 128),  # Pink/Purple
            "u_turn_forbidden": (0, 255, 255),  # Yellow
            "lane_a": (255, 0, 0),  # Blue
            "lane_b": (255, 128, 0),  # Cyan
        }
        return colors.get(zone_type, (128, 128, 128))

    def check_point_in_zone(self, point: Tuple[int, int], zone_id: str) -> bool:
        for zone in self.zones:
            if zone["id"] == zone_id and zone.get("enabled", True):
                return point_inside_polygon(point, zone["points"])
        return False

    def check_point_any_zone_type(
        self, point: Tuple[int, int], zone_type: str
    ) -> List[Dict[str, Any]]:
        """Returns all matching zones of a specific type where the point is inside."""
        matched = []
        for zone in self.get_zones_by_type(zone_type):
            if point_inside_polygon(point, zone["points"]):
                matched.append(zone)
        return matched

    def init_default_curves(self, h: int, w: int, roi_y1: int) -> None:
        """Initializes default curves for no_parking and shoulder_lane zones if not present."""
        plot_y = np.linspace(roi_y1, h - 20, 20)

        # Left curve default (no_parking)
        if not hasattr(self, "left_adaptive_curve"):
            zone = next((z for z in self.zones if z["id"] == "zone_parking_001"), None)
            if zone and len(zone["points"]) >= 4:
                pts = zone["points"]
                x1, y1 = pts[1]
                x2, y2 = pts[2]
                fit_x = np.interp(plot_y, [y1, y2], [x1, x2])
                self.left_adaptive_curve = np.array(
                    np.transpose(np.vstack([fit_x, plot_y])), dtype=np.int32
                )
            else:
                fit_x = np.linspace(int(w * 0.4), int(w * 0.15), 20)
                self.left_adaptive_curve = np.array(
                    np.transpose(np.vstack([fit_x, plot_y])), dtype=np.int32
                )

        # Right curve default (shoulder_lane)
        if not hasattr(self, "right_adaptive_curve"):
            zone = next((z for z in self.zones if z["id"] == "zone_shoulder_001"), None)
            if zone and len(zone["points"]) >= 4:
                pts = zone["points"]
                x1, y1 = pts[0]
                x2, y2 = pts[3]
                fit_x = np.interp(plot_y, [y1, y2], [x1, x2])
                self.right_adaptive_curve = np.array(
                    np.transpose(np.vstack([fit_x, plot_y])), dtype=np.int32
                )
            else:
                fit_x = np.linspace(int(w * 0.6), int(w * 0.85), 20)
                self.right_adaptive_curve = np.array(
                    np.transpose(np.vstack([fit_x, plot_y])), dtype=np.int32
                )

    def draw_zones(
        self,
        frame: np.ndarray,
        enabled_violations: Optional[List[str]] = None,
        source_type: str = "cctv",
        source_label: str = "",
    ) -> None:
        """Renders zone borders as premium lines/curves rather than full boxes."""
        ZONE_TO_VIOLATION_MAP = {
            "no_parking": ["illegal_parking", "restricted_area_stop"],
            "shoulder_lane": ["shoulder_lane_violation"],
            "red_light_stop_line": ["red_light_violation"],
            "u_turn_forbidden": ["illegal_u_turn"],
            "lane_a": ["unsafe_lane_change"],
            "lane_b": ["unsafe_lane_change"],
        }

        h, w = frame.shape[:2]
        is_bendungan = "bendungan" in str(source_label).lower()

        for zone in self.zones:
            if not zone.get("enabled", True) or not zone.get("points"):
                continue

            # Hide shoulder lane zone for CCTV
            if zone["type"] == "shoulder_lane" and source_type == "cctv":
                continue

            # Filter by enabled violations if provided
            if enabled_violations is not None:
                mapped_violations = ZONE_TO_VIOLATION_MAP.get(zone["type"], [])
                # If none of the mapped violations are enabled, skip drawing this zone
                if not any(v in enabled_violations for v in mapped_violations):
                    continue

            # Hide stop line zone if no traffic light has been detected recently
            if zone["type"] == "red_light_stop_line" and self.traffic_light_frames <= 0:
                continue

            # Hide u-turn zone if no u-turn/prohibited turn sign has been detected recently
            if zone["type"] == "u_turn_forbidden" and self.u_turn_sign_frames <= 0:
                continue

            color = self.get_zone_colors(zone["type"])

            # ── Drawing Road Boundaries as Curves instead of Boxes ──
            if zone["type"] in ["no_parking", "shoulder_lane"] and source_type != "cctv":
                curve_drawn = False
                if zone["type"] == "no_parking" and hasattr(
                    self, "left_adaptive_curve"
                ):
                    cv2.polylines(
                        frame, [self.left_adaptive_curve], False, color, 3, cv2.LINE_AA
                    )
                    mid_idx = len(self.left_adaptive_curve) // 2
                    lx, ly = self.left_adaptive_curve[mid_idx]
                    cv2.putText(
                        frame,
                        zone["name"],
                        (int(lx) - 70, int(ly)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        2,
                        cv2.LINE_AA,
                    )
                    curve_drawn = True
                elif zone["type"] == "shoulder_lane" and hasattr(
                    self, "right_adaptive_curve"
                ):
                    cv2.polylines(
                        frame, [self.right_adaptive_curve], False, color, 3, cv2.LINE_AA
                    )
                    mid_idx = len(self.right_adaptive_curve) // 2
                    rx, ry = self.right_adaptive_curve[mid_idx]
                    cv2.putText(
                        frame,
                        zone["name"],
                        (int(rx) + 15, int(ry)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        color,
                        2,
                        cv2.LINE_AA,
                    )
                    curve_drawn = True

                if not curve_drawn:
                    pts = np.array(zone["points"], dtype=np.int32)
                    if zone["type"] == "no_parking":
                        cv2.line(
                            frame, tuple(pts[1]), tuple(pts[2]), color, 3, cv2.LINE_AA
                        )
                        cv2.putText(
                            frame,
                            zone["name"],
                            tuple(pts[1]),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            color,
                            2,
                            cv2.LINE_AA,
                        )
                    else:
                        cv2.line(
                            frame, tuple(pts[0]), tuple(pts[3]), color, 3, cv2.LINE_AA
                        )
                        cv2.putText(
                            frame,
                            zone["name"],
                            tuple(pts[0]),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            color,
                            2,
                            cv2.LINE_AA,
                        )
            else:
                # Other zones (stop lines, lanes, u-turn) - draw as polylines only
                pts = np.array(zone["points"], dtype=np.int32)
                cv2.polylines(frame, [pts], True, color, 2, cv2.LINE_AA)

                x, y = zone["points"][0]
                label = f"{zone['name']} ({zone['type'].replace('_', ' ').title()})"
                cv2.putText(
                    frame,
                    label,
                    (int(x), int(y) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    2,
                    cv2.LINE_AA,
                )

    def adapt_zones_to_lanes(
        self,
        frame: np.ndarray,
        source_type: str = "cctv",
        source_label: Optional[str] = None,
        tracks: Optional[List[Any]] = None,
    ) -> None:
        """
        Dynamically detects road lane boundaries using vehicle trajectories (CCTV mode)
        or a pre-trained YOLOP model, then adapts active zones accordingly.
        """
        if source_type == "cctv":
            return
        if frame is None or frame.size == 0:
            return

        h, w = frame.shape[:2]
        roi_y1 = int(h * 0.40)

        # Load custom profile zones if specified for this source label
        profile = {}
        if source_label:
            profile = self.config.get("source_profiles.by_filename", {}).get(
                source_label, {}
            )

        self.has_custom_profile_zones = False
        if profile and "zones" in profile:
            self.has_custom_profile_zones = True
            custom_zones = []
            TYPE_TO_ID_MAP = {
                "no_parking": "zone_parking_001",
                "shoulder_lane": "zone_shoulder_001",
                "red_light_stop_line": "zone_stop_line_001",
                "u_turn_forbidden": "zone_u_turn_001",
                "lane_a": "zone_lane_a_001",
                "lane_b": "zone_lane_b_001",
            }
            for z_type, polys in profile["zones"].items():
                for i, poly in enumerate(polys):
                    z_id = TYPE_TO_ID_MAP.get(
                        z_type, f"profile_{source_label}_{z_type}_{i}"
                    )
                    custom_zones.append(
                        {
                            "id": z_id,
                            "name": f"{z_type.replace('_', ' ').title()} {i + 1}",
                            "type": z_type,
                            "enabled": True,
                            "points": poly,
                            "rule_config": {
                                "min_seconds": float(
                                    self.config.get(
                                        "violation.illegal_parking_seconds", 5
                                    )
                                )
                            },
                        }
                    )
            if custom_zones:
                if (
                    not hasattr(self, "current_source_label")
                    or self.current_source_label != source_label
                ):
                    self.zones = custom_zones
                    self.current_source_label = source_label
                    self.density_map = None
                    if hasattr(self, "left_adaptive_curve"):
                        delattr(self, "left_adaptive_curve")
                    if hasattr(self, "right_adaptive_curve"):
                        delattr(self, "right_adaptive_curve")
                    if hasattr(self, "base_zones"):
                        delattr(self, "base_zones")
                    self.cctv_lanes_fitted = False
        else:
            if (
                hasattr(self, "current_source_label")
                and self.current_source_label != source_label
            ):
                self.zones = list(self.default_zones)
                self.current_source_label = source_label
                self.density_map = None
                if hasattr(self, "left_adaptive_curve"):
                    delattr(self, "left_adaptive_curve")
                if hasattr(self, "right_adaptive_curve"):
                    delattr(self, "right_adaptive_curve")
                if hasattr(self, "base_zones"):
                    delattr(self, "base_zones")
                self.cctv_lanes_fitted = False

        # Initialize default curves if not present
        self.init_default_curves(h, w, roi_y1)

        # Increment frame count
        self.frame_count += 1

        # Initialize density map if None
        if self.density_map is None or self.density_map.shape != (h, w):
            self.density_map = np.zeros((h, w), dtype=np.float32)

        # Skip expensive lane adaptation every N frames to improve FPS
        # For CCTV: run adapt every 15 frames until fitted, then skip
        # For dashcam: run adapt every 10 frames after initial 30 frames of accumulation
        run_lane_adapt = True
        if source_type == "cctv":
            if self.cctv_lanes_fitted:
                run_lane_adapt = False
            elif self.frame_count % 15 != 0:
                run_lane_adapt = False
        else:
            if self.frame_count > 30 and self.frame_count % 10 != 0:
                run_lane_adapt = False

        # ── Mode A: CCTV Mode (Accumulated Traffic Density + Component Overlap Matching) ──
        if source_type == "cctv":
            # Accumulate vehicle tracks into density map
            if tracks is not None:
                for track in tracks:
                    if getattr(track, "class_name", "") in {
                        "car",
                        "motorcycle",
                        "bus",
                        "truck",
                        "jaklingko",
                        "angkot_merah",
                        "angkot_hijau",
                        "angkot_biru",
                        "transjakarta",
                        "metrotrans",
                    }:
                        x1, y1, x2, y2 = track.bbox
                        x1, y1 = max(0, int(x1)), max(0, int(y1))
                        x2, y2 = min(w - 1, int(x2)), min(h - 1, int(y2))
                        if x2 > x1 and y2 > y1:
                            self.density_map[y1:y2, x1:x2] += 1.0

            # Skip heavy lane fitting if not scheduled this frame
            if not run_lane_adapt or self.cctv_lanes_fitted:
                return

            max_val = np.max(self.density_map)

            # Threshold density map to keep active lanes
            thresh_val = max(2.0, max_val * 0.05)
            binary_mask = (self.density_map >= thresh_val).astype(np.uint8)

            # Integrate YOLOP segmentation mask if available to guide density mapping
            use_yolop_model = self.config.get("models.use_yolop_model", False)
            if use_yolop_model:
                if self.yolop_model is None:
                    import torch

                    try:
                        print("[INFO] Lazy-loading YOLOP model from PyTorch Hub...")
                        self.yolop_model = torch.hub.load(
                            "hustvl/yolop", "yolop", pretrained=True, trust_repo=True
                        )
                        self.yolop_model.eval()
                    except Exception as e:
                        print(f"[ERROR] Failed to load YOLOP model: {e}")
                        use_yolop_model = False

                if self.yolop_model is not None:
                    try:
                        import torch

                        # Preprocess frame for YOLOP
                        img_resized = cv2.resize(frame, (640, 384))
                        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
                        img_tensor = torch.from_numpy(img_rgb).float() / 255.0
                        img_tensor = img_tensor.permute(2, 0, 1)
                        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
                        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
                        img_tensor = (img_tensor - mean) / std
                        img_tensor = img_tensor.unsqueeze(0)

                        with torch.no_grad():
                            det_out, da_seg_out, ll_seg_out = self.yolop_model(
                                img_tensor
                            )

                        da_seg_mask = (
                            torch.argmax(da_seg_out, dim=1)
                            .squeeze()
                            .cpu()
                            .numpy()
                            .astype(np.uint8)
                        )
                        if np.sum(da_seg_mask) > 100:
                            da_seg_mask_resized = cv2.resize(da_seg_mask, (w, h))
                            binary_mask = cv2.bitwise_and(
                                binary_mask, da_seg_mask_resized
                            )
                    except Exception as exc:
                        print(f"[WARN] YOLOP road segmentation inference failed: {exc}")

            # Apply horizontal dilation to bridge gaps between separate lanes
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (70, 1))
            dilated_mask = cv2.dilate(binary_mask, kernel, iterations=1)

            # Construct default road area mask for overlap matching
            default_poly = []
            target_y = np.linspace(roi_y1, h - 20, 20)
            default_left_x = self.left_adaptive_curve[:, 0]
            default_right_x = self.right_adaptive_curve[:, 0]
            for i in range(len(target_y)):
                default_poly.append([default_left_x[i], target_y[i]])
            for i in range(len(target_y) - 1, -1, -1):
                default_poly.append([default_right_x[i], target_y[i]])

            default_road_mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(default_road_mask, [np.array(default_poly, dtype=np.int32)], 1)

            # Find connected components and select component with max default road overlap
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
                dilated_mask
            )
            best_label = 0
            max_overlap = 0
            for label in range(1, num_labels):
                overlap = np.sum((labels == label) & (default_road_mask == 1))
                if overlap > max_overlap:
                    max_overlap = overlap
                    best_label = label

            if best_label > 0:
                target_road_mask = labels == best_label

                left_pts = []
                right_pts = []
                for y in target_y:
                    y_int = int(y)
                    active_x = np.where(target_road_mask[y_int, :] == 1)[0]
                    if len(active_x) > 0:
                        left_pts.append([min(active_x), y])
                        right_pts.append([max(active_x), y])

                fitted_left_x = None
                fitted_right_x = None

                # Fit Left Curve with robust trend filtering
                if len(left_pts) >= 5:
                    left_pts = np.array(left_pts)
                    slope, intercept = np.polyfit(left_pts[:, 1], left_pts[:, 0], 1)
                    residuals = np.abs(
                        left_pts[:, 0] - (slope * left_pts[:, 1] + intercept)
                    )
                    inliers = residuals < 50
                    left_pts_filtered = left_pts[inliers]

                    if len(left_pts_filtered) >= 3:
                        left_fit = np.polyfit(
                            left_pts_filtered[:, 1], left_pts_filtered[:, 0], 2
                        )
                    else:
                        left_fit = np.polyfit(left_pts[:, 1], left_pts[:, 0], 2)
                    fitted_left_x = (
                        left_fit[0] * target_y**2 + left_fit[1] * target_y + left_fit[2]
                    )

                # Fit Right Curve
                if len(right_pts) >= 5:
                    right_pts = np.array(right_pts)
                    slope_r, intercept_r = np.polyfit(
                        right_pts[:, 1], right_pts[:, 0], 1
                    )
                    residuals_r = np.abs(
                        right_pts[:, 0] - (slope_r * right_pts[:, 1] + intercept_r)
                    )
                    inliers_r = residuals_r < 50
                    right_pts_filtered = right_pts[inliers_r]

                    if len(right_pts_filtered) >= 3:
                        right_fit = np.polyfit(
                            right_pts_filtered[:, 1], right_pts_filtered[:, 0], 2
                        )
                    else:
                        right_fit = np.polyfit(right_pts[:, 1], right_pts[:, 0], 2)
                    fitted_right_x = (
                        right_fit[0] * target_y**2
                        + right_fit[1] * target_y
                        + right_fit[2]
                    )

                # Update curves if successfully fitted
                if fitted_left_x is not None and fitted_right_x is not None:
                    # Prevent crossing at vanishing point
                    for i in range(len(target_y)):
                        if fitted_left_x[i] >= fitted_right_x[i] - 10:
                            mid = (fitted_left_x[i] + fitted_right_x[i]) / 2.0
                            fitted_left_x[i] = mid - 5
                            fitted_right_x[i] = mid + 5

                    self.left_adaptive_curve[:, 0] = fitted_left_x.astype(np.int32)
                    self.right_adaptive_curve[:, 0] = fitted_right_x.astype(np.int32)

                    # Freeze curves after collecting enough data
                    if self.frame_count >= 50 or max_val >= 6.0:
                        self.cctv_lanes_fitted = True
                        print(
                            f"[INFO] CCTV lane boundaries successfully fitted and frozen using traffic density for {source_label}."
                        )

        # ── Mode B: Dashcam Mode (Frame-by-Frame YOLOP/YOLOv8 Segmentation) ──
        else:
            if not run_lane_adapt:
                return
            use_yolop_model = self.config.get("models.use_yolop_model", False)
            use_lane_model = self.config.get("models.use_lane_model", True)

            # Lazy-load models
            if use_yolop_model and self.yolop_model is None:
                import torch

                try:
                    self.yolop_model = torch.hub.load(
                        "hustvl/yolop", "yolop", pretrained=True, trust_repo=True
                    )
                    self.yolop_model.eval()
                except Exception:
                    use_yolop_model = False

            if not use_yolop_model and use_lane_model and self.lane_model is None:
                lane_model_path = self.config.get(
                    "models.lane_model_path", "models/yolov8m-lane-seg.pt"
                )
                if os.path.exists(lane_model_path):
                    from ultralytics import YOLO

                    try:
                        self.lane_model = YOLO(lane_model_path)
                    except Exception:
                        use_lane_model = False

            lane_fitted_this_frame = False

            if use_yolop_model and self.yolop_model is not None:
                try:
                    import torch

                    img_resized = cv2.resize(frame, (640, 384))
                    img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
                    img_tensor = torch.from_numpy(img_rgb).float() / 255.0
                    img_tensor = img_tensor.permute(2, 0, 1)
                    mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
                    std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
                    img_tensor = (img_tensor - mean) / std
                    img_tensor = img_tensor.unsqueeze(0)

                    with torch.no_grad():
                        det_out, da_seg_out, ll_seg_out = self.yolop_model(img_tensor)

                    da_seg_mask = (
                        torch.argmax(da_seg_out, dim=1).squeeze().cpu().numpy()
                    )
                    target_y = np.linspace(roi_y1, h - 20, 20)
                    left_pts = []
                    right_pts = []

                    ref_left_xs = self.left_adaptive_curve[:, 0]
                    ref_right_xs = self.right_adaptive_curve[:, 0]
                    margin_mask = 120

                    for i, y in enumerate(target_y):
                        y_mask = int(y * 384.0 / h)
                        y_mask = max(0, min(383, y_mask))
                        ref_left_mask = ref_left_xs[i] * 640.0 / w
                        ref_right_mask = ref_right_xs[i] * 640.0 / w

                        active_x = np.where(da_seg_mask[y_mask, :] == 1)[0]
                        left_candidates = []
                        right_candidates = []
                        if len(active_x) > 0:
                            left_candidates = active_x[
                                (active_x >= ref_left_mask - margin_mask)
                                & (active_x <= ref_left_mask + margin_mask)
                            ]
                            right_candidates = active_x[
                                (active_x >= ref_right_mask - margin_mask)
                                & (active_x <= ref_right_mask + margin_mask)
                            ]

                        if len(left_candidates) > 0:
                            left_pts.append([min(left_candidates) * w / 640.0, y])
                        else:
                            left_pts.append([ref_left_xs[i], y])

                        if len(right_candidates) > 0:
                            right_pts.append([max(right_candidates) * w / 640.0, y])
                        else:
                            right_pts.append([ref_right_xs[i], y])

                    left_pts = np.array(left_pts)
                    left_fit = np.polyfit(left_pts[:, 1], left_pts[:, 0], 2)
                    left_fitx = (
                        left_fit[0] * target_y**2 + left_fit[1] * target_y + left_fit[2]
                    )

                    right_pts = np.array(right_pts)
                    right_fit = np.polyfit(right_pts[:, 1], right_pts[:, 0], 2)
                    right_fitx = (
                        right_fit[0] * target_y**2
                        + right_fit[1] * target_y
                        + right_fit[2]
                    )

                    # Enforce separation
                    for i in range(len(target_y)):
                        if left_fitx[i] >= right_fitx[i] - 10:
                            mid = (left_fitx[i] + right_fitx[i]) / 2.0
                            left_fitx[i] = mid - 5
                            right_fitx[i] = mid + 5

                    alpha_curve = 0.35
                    self.left_adaptive_curve[:, 0] = (
                        alpha_curve * left_fitx
                        + (1 - alpha_curve) * self.left_adaptive_curve[:, 0]
                    ).astype(np.int32)
                    self.right_adaptive_curve[:, 0] = (
                        alpha_curve * right_fitx
                        + (1 - alpha_curve) * self.right_adaptive_curve[:, 0]
                    ).astype(np.int32)
                    lane_fitted_this_frame = True
                except Exception:
                    pass

            if (
                not lane_fitted_this_frame
                and use_lane_model
                and self.lane_model is not None
            ):
                try:
                    results = self.lane_model(frame, device="cpu", verbose=False)
                    if results and len(results) > 0 and results[0].masks is not None:
                        res = results[0]
                        masks = res.masks.data.cpu().numpy()
                        classes = res.boxes.cls.cpu().numpy()

                        target_y = np.linspace(roi_y1, h - 20, 20)
                        left_pts_x, left_pts_y = [], []
                        right_pts_x, right_pts_y = [], []

                        mask_h, mask_w = masks.shape[1:3]
                        scale_y, scale_x = h / mask_h, w / mask_w

                        for i, cls in enumerate(classes):
                            if int(cls) == 0:  # solid boundary
                                mask = masks[i]
                                ys, xs = np.where(mask > 0.5)
                                if len(xs) > 0:
                                    orig_xs = xs * scale_x
                                    orig_ys = ys * scale_y
                                    mean_x = np.mean(orig_xs)
                                    if mean_x < w / 2:
                                        left_pts_x.extend(orig_xs)
                                        left_pts_y.extend(orig_ys)
                                    else:
                                        right_pts_x.extend(orig_xs)
                                        right_pts_y.extend(orig_ys)

                        left_fitx = None
                        if len(left_pts_x) >= 30:
                            y_bins = np.linspace(roi_y1, h - 20, 30)
                            bin_indices = np.digitize(left_pts_y, y_bins)
                            mean_xs, mean_ys = [], []
                            for b in range(1, len(y_bins)):
                                in_bin = np.array(left_pts_x)[bin_indices == b]
                                if len(in_bin) > 0:
                                    mean_xs.append(np.mean(in_bin))
                                    mean_ys.append(y_bins[b - 1])
                            if len(mean_xs) >= 3:
                                left_fit = np.polyfit(mean_ys, mean_xs, 2)
                                left_fitx = (
                                    left_fit[0] * target_y**2
                                    + left_fit[1] * target_y
                                    + left_fit[2]
                                )

                        right_fitx = None
                        if len(right_pts_x) >= 30:
                            y_bins = np.linspace(roi_y1, h - 20, 30)
                            bin_indices = np.digitize(right_pts_y, y_bins)
                            mean_xs, mean_ys = [], []
                            for b in range(1, len(y_bins)):
                                in_bin = np.array(right_pts_x)[bin_indices == b]
                                if len(in_bin) > 0:
                                    mean_xs.append(np.mean(in_bin))
                                    mean_ys.append(y_bins[b - 1])
                            if len(mean_xs) >= 3:
                                right_fit = np.polyfit(mean_ys, mean_xs, 2)
                                right_fitx = (
                                    right_fit[0] * target_y**2
                                    + right_fit[1] * target_y
                                    + right_fit[2]
                                )

                        if left_fitx is not None or right_fitx is not None:
                            left_fitx = (
                                left_fitx
                                if left_fitx is not None
                                else self.left_adaptive_curve[:, 0]
                            )
                            right_fitx = (
                                right_fitx
                                if right_fitx is not None
                                else self.right_adaptive_curve[:, 0]
                            )

                            # Enforce separation
                            for i in range(len(target_y)):
                                if left_fitx[i] >= right_fitx[i] - 10:
                                    mid = (left_fitx[i] + right_fitx[i]) / 2.0
                                    left_fitx[i] = mid - 5
                                    right_fitx[i] = mid + 5

                            alpha_curve = 0.35
                            self.left_adaptive_curve[:, 0] = (
                                alpha_curve * left_fitx
                                + (1 - alpha_curve) * self.left_adaptive_curve[:, 0]
                            ).astype(np.int32)
                            self.right_adaptive_curve[:, 0] = (
                                alpha_curve * right_fitx
                                + (1 - alpha_curve) * self.right_adaptive_curve[:, 0]
                            ).astype(np.int32)
                            lane_fitted_this_frame = True
                except Exception:
                    pass

        # If the stream does not have custom profile zones, we generate them dynamically
        if not self.has_custom_profile_zones:
            target_y = np.linspace(roi_y1, h - 20, 20)
            left_xs = self.left_adaptive_curve[:, 0]
            right_xs = self.right_adaptive_curve[:, 0]

            # Construct No Parking Zone (left 30% of road)
            no_parking_poly = []
            for i in range(len(target_y)):
                no_parking_poly.append([int(left_xs[i]), int(target_y[i])])
            for i in range(len(target_y) - 1, -1, -1):
                mid_x = left_xs[i] + 0.3 * (right_xs[i] - left_xs[i])
                no_parking_poly.append([int(mid_x), int(target_y[i])])

            # Construct Shoulder Lane Zone (right 30% of road)
            shoulder_poly = []
            for i in range(len(target_y)):
                mid_x = left_xs[i] + 0.7 * (right_xs[i] - left_xs[i])
                shoulder_poly.append([int(mid_x), int(target_y[i])])
            for i in range(len(target_y) - 1, -1, -1):
                shoulder_poly.append([int(right_xs[i]), int(target_y[i])])

            dynamic_zones = [
                {
                    "id": "zone_parking_001",
                    "name": "No Parking Zone (Auto)",
                    "type": "no_parking",
                    "enabled": True,
                    "points": no_parking_poly,
                    "rule_config": {
                        "min_seconds": float(
                            self.config.get("violation.illegal_parking_seconds", 5)
                        )
                    },
                },
                {
                    "id": "zone_shoulder_001",
                    "name": "Shoulder Lane (Auto)",
                    "type": "shoulder_lane",
                    "enabled": True,
                    "points": shoulder_poly,
                    "rule_config": {
                        "min_seconds": float(
                            self.config.get("violation.illegal_parking_seconds", 5)
                        )
                    },
                },
            ]
            self.zones = dynamic_zones

        if self.has_custom_profile_zones:
            # Initialize base zones if not already done
            if not hasattr(self, "base_zones"):
                import copy

                self.base_zones = copy.deepcopy(self.zones)

            # Dynamically adjust zone polygon points clockwise/counter-clockwise to follow curve shape
            alpha = 0.12
            for zone, base_zone in zip(self.zones, self.base_zones):
                if not zone.get("points") or len(zone["points"]) < 4:
                    continue

                pts = [list(p) for p in zone["points"]]
                base_pts = [list(p) for p in base_zone["points"]]

                # ── Adjust No Parking Zone 1 (Left) ──
                if zone["id"] == "zone_parking_001":
                    y_top = pts[1][1]
                    y_bottom = pts[2][1]

                    target_x_top = int(
                        np.interp(
                            y_top,
                            self.left_adaptive_curve[:, 1],
                            self.left_adaptive_curve[:, 0],
                        )
                    )
                    target_x_bottom = int(
                        np.interp(
                            y_bottom,
                            self.left_adaptive_curve[:, 1],
                            self.left_adaptive_curve[:, 0],
                        )
                    )

                    target_x_top = max(
                        base_pts[1][0] - 100, min(base_pts[1][0] + 100, target_x_top)
                    )
                    target_x_bottom = max(
                        base_pts[2][0] - 150, min(base_pts[2][0] + 150, target_x_bottom)
                    )

                    pts[1][0] = int(alpha * target_x_top + (1 - alpha) * pts[1][0])
                    pts[2][0] = int(alpha * target_x_bottom + (1 - alpha) * pts[2][0])

                # ── Adjust Shoulder Lane Zone 1 (Right) ──
                elif zone["id"] == "zone_shoulder_001":
                    y_top = pts[0][1]
                    y_bottom = pts[3][1]

                    target_x_top = int(
                        np.interp(
                            y_top,
                            self.right_adaptive_curve[:, 1],
                            self.right_adaptive_curve[:, 0],
                        )
                    )
                    target_x_bottom = int(
                        np.interp(
                            y_bottom,
                            self.right_adaptive_curve[:, 1],
                            self.right_adaptive_curve[:, 0],
                        )
                    )

                    target_x_top = max(
                        base_pts[0][0] - 100, min(base_pts[0][0] + 100, target_x_top)
                    )
                    target_x_bottom = max(
                        base_pts[3][0] - 150, min(base_pts[3][0] + 150, target_x_bottom)
                    )

                    pts[0][0] = int(alpha * target_x_top + (1 - alpha) * pts[0][0])
                    pts[3][0] = int(alpha * target_x_bottom + (1 - alpha) * pts[3][0])

                # ── Adjust Lane A (Lane A) ──
                elif zone["id"] == "zone_lane_a_001":
                    y_top = pts[0][1]
                    y_bottom = pts[3][1]

                    target_x_top = int(
                        np.interp(
                            y_top,
                            self.left_adaptive_curve[:, 1],
                            self.left_adaptive_curve[:, 0],
                        )
                    )
                    target_x_bottom = int(
                        np.interp(
                            y_bottom,
                            self.left_adaptive_curve[:, 1],
                            self.left_adaptive_curve[:, 0],
                        )
                    )

                    target_x_top = max(
                        base_pts[0][0] - 100, min(base_pts[0][0] + 100, target_x_top)
                    )
                    target_x_bottom = max(
                        base_pts[3][0] - 150, min(base_pts[3][0] + 150, target_x_bottom)
                    )

                    pts[0][0] = int(alpha * target_x_top + (1 - alpha) * pts[0][0])
                    pts[3][0] = int(alpha * target_x_bottom + (1 - alpha) * pts[3][0])

                # ── Adjust Lane B (Lane B) ──
                elif zone["id"] == "zone_lane_b_001":
                    y_top = pts[1][1]
                    y_bottom = pts[2][1]

                    target_x_top = int(
                        np.interp(
                            y_top,
                            self.right_adaptive_curve[:, 1],
                            self.right_adaptive_curve[:, 0],
                        )
                    )
                    target_x_bottom = int(
                        np.interp(
                            y_bottom,
                            self.right_adaptive_curve[:, 1],
                            self.right_adaptive_curve[:, 0],
                        )
                    )

                    target_x_top = max(
                        base_pts[1][0] - 100, min(base_pts[1][0] + 100, target_x_top)
                    )
                    target_x_bottom = max(
                        base_pts[2][0] - 150, min(base_pts[2][0] + 150, target_x_bottom)
                    )

                    pts[1][0] = int(alpha * target_x_top + (1 - alpha) * pts[1][0])
                    pts[2][0] = int(alpha * target_x_bottom + (1 - alpha) * pts[2][0])

                zone["points"] = pts
