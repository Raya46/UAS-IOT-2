import type { Incident } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

const PUBLIC_SNAPSHOT_FILES = new Set([
  "angkot-berhenti-sembarangan.png",
  "angkot-parkir-sembarangan.png",
  "busway_violation_2.png",
  "default.png",
  "kemacetan.png",
  "kemacetan_2.png",
  "kemacetan_3.png",
  "kemacetan_4.png",
  "kemacetan_5.png",
  "lawan_arah.png",
  "mobil-putih-nerobos-lampu-merah-dari-arah-depan.png",
  "motor-potong-lajur-mobil-dari-arah-kanan-ke-kiri.png",
  "motor-putar-arah-sembarangan-plat-nomor.png",
  "motor-putar-arah-sembarangan.png",
  "parkir_liar.png",
  "parkir_liar_2.png",
  "prima-jasa-nyalip-dari-bahu-jalan.png",
  "taksi-melanggar-rambu-dilarang-belok-kanan.png",
  "toyota-camry-nyalip-dari-bahu-jalan.png",
  "etle_logo.png",
]);

const SNAPSHOT_BY_TYPE: Record<string, string> = {
  illegal_parking: "/snapshots/parkir_liar.png",
  busway_violation: "/snapshots/busway_violation_2.png",
  congestion: "/snapshots/kemacetan.png",
  wrong_way: "/snapshots/lawan_arah.png",
  hazard_lights: "/snapshots/default.png",
  red_light_violation: "/snapshots/mobil-putih-nerobos-lampu-merah-dari-arah-depan.png",
  illegal_u_turn: "/snapshots/motor-putar-arah-sembarangan.png",
  unsafe_lane_change: "/snapshots/motor-potong-lajur-mobil-dari-arah-kanan-ke-kiri.png",
  shoulder_violation: "/snapshots/prima-jasa-nyalip-dari-bahu-jalan.png",
};

export interface EvidenceMetadata {
  description?: string;
  vehicle_type?: string;
  plate_number?: string;
  plate_note?: string;
}

const EVIDENCE_BY_SNAPSHOT: Record<string, EvidenceMetadata> = {
  "angkot-parkir-sembarangan.png": {
    description: "Angkot parkir sembarangan.",
    vehicle_type: "angkot",
    plate_number: "D 1914 AP",
  },
  "angkot-berhenti-sembarangan.png": {
    description: "Angkot berhenti sembarangan dan mengganggu arus kendaraan.",
    vehicle_type: "angkot",
    plate_number: "D 1914 AP",
  },
  "prima-jasa-nyalip-dari-bahu-jalan.png": {
    description: "Bus Prima Jasa dan Toyota Camry menyalip dari bahu jalan dan memaksa masuk di Entrance Rest.",
    vehicle_type: "bus",
    plate_number: "B 1485 PAI",
    plate_note: "Toyota Camry terbaca B 1485 PAI; bus Primajasa dipakai sebagai bukti visual karena plat bus tidak terlihat.",
  },
  "toyota-camry-nyalip-dari-bahu-jalan.png": {
    description: "Toyota Camry menyalip dari bahu jalan dan memaksa masuk di Entrance Rest.",
    vehicle_type: "car",
    plate_number: "B 1485 PAI",
  },
  "mobil-putih-nerobos-lampu-merah-dari-arah-depan.png": {
    description: "Mobil putih menerobos lampu merah dari arah depan.",
    vehicle_type: "car",
    plate_note: "Plat nomor tidak terlihat pada frame bukti.",
  },
  "motor-putar-arah-sembarangan.png": {
    description: "Motor putar arah sembarangan.",
    vehicle_type: "motorcycle",
    plate_number: "BM 6446 GD",
  },
  "motor-putar-arah-sembarangan-plat-nomor.png": {
    description: "Motor putar arah sembarangan.",
    vehicle_type: "motorcycle",
    plate_number: "BM 6446 GD",
  },
  "motor-potong-lajur-mobil-dari-arah-kanan-ke-kiri.png": {
    description: "Motor potong lajur mobil dari kanan ke kiri.",
    vehicle_type: "motorcycle",
    plate_note: "Plat nomor tidak terlihat pada frame bukti.",
  },
  "taksi-melanggar-rambu-dilarang-belok-kanan.png": {
    description: "Taksi Bluebird berputar arah/berbelok kanan di lajur lampu merah yang dilarang.",
    vehicle_type: "taxi",
    plate_number: "B 1172 TUC",
  },
  "parkir_liar.png": {
    plate_number: "B 9442 GOX",
  },
  "parkir_liar_2.png": {
    plate_number: "B 1234 KJP",
  },
  "busway_violation_2.png": {
    plate_number: "B 7721 TJQ",
  },
};

export const DASHCAM_EVIDENCE_BY_VIDEO: Record<string, EvidenceMetadata & { snapshot_url: string }> = {
  "angkot-parkir-sembarangan.mp4": {
    snapshot_url: "/snapshots/angkot-parkir-sembarangan.png",
    ...EVIDENCE_BY_SNAPSHOT["angkot-parkir-sembarangan.png"],
  },
  "Bus Prima Jasa dan Toyota Camry, menyalip dari bahu jalan dan memaksa masuk.Entrance Rest A.mp4": {
    snapshot_url: "/snapshots/prima-jasa-nyalip-dari-bahu-jalan.png",
    ...EVIDENCE_BY_SNAPSHOT["prima-jasa-nyalip-dari-bahu-jalan.png"],
  },
  "mobil-putih-menerobos-lampu-merah-dari-arah-depan.mp4": {
    snapshot_url: "/snapshots/mobil-putih-nerobos-lampu-merah-dari-arah-depan.png",
    ...EVIDENCE_BY_SNAPSHOT["mobil-putih-nerobos-lampu-merah-dari-arah-depan.png"],
  },
  "mobil-yang-parkir-pada-kanan-kiri-ruas-jalan-tertib.mp4": {
    snapshot_url: "/snapshots/motor-putar-arah-sembarangan.png",
    ...EVIDENCE_BY_SNAPSHOT["motor-putar-arah-sembarangan.png"],
  },
  "motor-potong-lajur-mobil-dari-kanan-ke-kiri.mp4": {
    snapshot_url: "/snapshots/motor-potong-lajur-mobil-dari-arah-kanan-ke-kiri.png",
    ...EVIDENCE_BY_SNAPSHOT["motor-potong-lajur-mobil-dari-arah-kanan-ke-kiri.png"],
  },
  "taksi-berputar-arah-di-lampu-merah-yang-dilarang.mp4": {
    snapshot_url: "/snapshots/taksi-melanggar-rambu-dilarang-belok-kanan.png",
    ...EVIDENCE_BY_SNAPSHOT["taksi-melanggar-rambu-dilarang-belok-kanan.png"],
  },
};

function getSnapshotBasename(snapshotUrl?: string): string {
  return snapshotUrl?.trim().split(/[\\/]/).pop() || "";
}

export function getEvidenceMetadataForSnapshot(snapshotUrl?: string): EvidenceMetadata {
  return EVIDENCE_BY_SNAPSHOT[getSnapshotBasename(snapshotUrl)] || {};
}

export function getEvidenceMetadataForVideo(videoFile?: string): (EvidenceMetadata & { snapshot_url?: string }) {
  return videoFile ? DASHCAM_EVIDENCE_BY_VIDEO[videoFile] || {} : {};
}

export function enrichIncidentWithEvidence(incident: Incident): Incident {
  const metadata = getEvidenceMetadataForSnapshot(incident.snapshot_url);
  return {
    ...incident,
    description: incident.description || metadata.description,
    vehicle_type: incident.vehicle_type || metadata.vehicle_type,
    plate_number: incident.plate_number || metadata.plate_number,
    plate_note: incident.plate_note || metadata.plate_note,
  };
}

export function getIncidentSnapshotUrl(
  incident: Pick<Incident, "snapshot_url" | "type">,
): string {
  const fallback = SNAPSHOT_BY_TYPE[incident.type] || "/snapshots/default.png";
  const snapshotUrl = incident.snapshot_url?.trim();

  if (!snapshotUrl) return fallback;
  if (/^https?:\/\//i.test(snapshotUrl)) {
    return snapshotUrl;
  }
  if (snapshotUrl.startsWith("/api/")) {
    return `${API_BASE}${snapshotUrl}`;
  }
  if (snapshotUrl.startsWith("/snapshots/")) {
    return snapshotUrl;
  }

  const basename = snapshotUrl.split(/[\\/]/).pop() || "";
  if (PUBLIC_SNAPSHOT_FILES.has(basename)) {
    return `/snapshots/${basename}`;
  }

  return fallback;
}
