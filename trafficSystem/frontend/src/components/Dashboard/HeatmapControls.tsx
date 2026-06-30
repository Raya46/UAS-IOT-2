const VIOLATION_TYPES = [
  { value: "", label: "Semua Tipe" },
  { value: "illegal_parking", label: "Parkir Liar" },
  { value: "busway_violation", label: "Pelanggaran Busway" },
  { value: "congestion", label: "Kemacetan" },
  { value: "wrong_way", label: "Lawan Arah" },
];

const DAY_LABELS = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];

interface HeatmapFilters {
  days: number;
  hourFrom: number;
  hourTo: number;
  dayOfWeek?: number;
  violationType?: string;
}

interface Props {
  filters: HeatmapFilters;
  onFiltersChange: (f: HeatmapFilters) => void;
  visible: boolean;
  onVisibilityToggle: () => void;
}

export function HeatmapControls({ filters, onFiltersChange, visible, onVisibilityToggle }: Props) {
  return (
    <div style={{
      padding: 14, background: "rgb(var(--color-surface-matte))",
      border: "1px solid rgb(var(--color-outline-variant))", borderRadius: 14,
      boxShadow: "0 1px 3px rgba(0, 0, 0, 0.02), 0 1px 2px rgba(0, 0, 0, 0.04)"
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <span style={{ color: "rgb(48 49 139)", fontSize: 12, fontWeight: 700, display: "flex", alignItems: "center", gap: 6 }}>
          <span className="material-symbols-outlined" style={{ fontSize: 16 }}>analytics</span>
          Violation Heatmap
        </span>
        <button
          onClick={onVisibilityToggle}
          style={{
            background: visible ? "rgb(var(--color-primary-fixed) / 0.18)" : "transparent",
            border: `1px solid ${visible ? "rgb(var(--color-primary-fixed))" : "rgb(var(--color-outline-variant))"}`,
            color: visible ? "rgb(var(--color-primary))" : "rgb(var(--color-on-surface-variant))",
            borderRadius: 8, padding: "3px 10px", fontSize: 11, cursor: "pointer",
            fontWeight: 600,
            transition: "all 0.2s"
          }}
        >
          {visible ? "Aktif" : "Non-aktif"}
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {/* Rentang hari */}
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
            <label style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 10, fontWeight: 500 }}>Rentang Analisis</label>
            <span style={{ color: "rgb(var(--color-on-surface))", fontSize: 10, fontWeight: 600 }}>{filters.days} Hari</span>
          </div>
          <input
            type="range" min={7} max={90} value={filters.days}
            onChange={(e) => onFiltersChange({ ...filters, days: +e.target.value })}
            style={{ width: "100%", accentColor: "rgb(48 49 139)" }}
          />
        </div>

        {/* Filter jam */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 10, fontWeight: 500, minWidth: 32 }}>Jam:</label>
          <select
            value={filters.hourFrom}
            onChange={(e) => onFiltersChange({ ...filters, hourFrom: +e.target.value })}
            style={{ background: "rgb(var(--color-surface-container-low))", color: "rgb(var(--color-on-surface))", border: "1px solid rgb(var(--color-outline-variant))", borderRadius: 8, fontSize: 11, padding: "3px 8px", cursor: "pointer", outline: "none" }}
          >
            {Array.from({ length: 24 }, (_, i) => (
              <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
            ))}
          </select>
          <span style={{ color: "rgb(var(--color-on-surface-variant))", fontSize: 10 }}>s/d</span>
          <select
            value={filters.hourTo}
            onChange={(e) => onFiltersChange({ ...filters, hourTo: +e.target.value })}
            style={{ background: "rgb(var(--color-surface-container-low))", color: "rgb(var(--color-on-surface))", border: "1px solid rgb(var(--color-outline-variant))", borderRadius: 8, fontSize: 11, padding: "3px 8px", cursor: "pointer", outline: "none" }}
          >
            {Array.from({ length: 24 }, (_, i) => (
              <option key={i} value={i}>{String(i).padStart(2, "0")}:00</option>
            ))}
          </select>
        </div>

        {/* Filter hari */}
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 2 }}>
          <button
            onClick={() => onFiltersChange({ ...filters, dayOfWeek: undefined })}
            style={{
              background: filters.dayOfWeek === undefined ? "rgb(var(--color-surface-container-high))" : "rgb(var(--color-surface-container-low))",
              border: `1px solid ${filters.dayOfWeek === undefined ? "rgb(var(--color-outline))" : "rgb(var(--color-outline-variant))"}`,
              color: filters.dayOfWeek === undefined ? "rgb(var(--color-on-surface))" : "rgb(var(--color-on-surface-variant))",
              borderRadius: 6, padding: "3px 8px", fontSize: 10, cursor: "pointer",
              fontWeight: 500, transition: "all 0.15s"
            }}
          >
            Semua
          </button>
          {DAY_LABELS.map((label, idx) => (
            <button
              key={idx}
              onClick={() => onFiltersChange({ ...filters, dayOfWeek: filters.dayOfWeek === idx ? undefined : idx })}
              style={{
                background: filters.dayOfWeek === idx ? "rgb(var(--color-primary-fixed) / 0.18)" : "rgb(var(--color-surface-container-low))",
                border: `1px solid ${filters.dayOfWeek === idx ? "rgb(var(--color-primary-fixed))" : "rgb(var(--color-outline-variant))"}`,
                color: filters.dayOfWeek === idx ? "rgb(var(--color-primary))" : "rgb(var(--color-on-surface-variant))",
                borderRadius: 6, padding: "3px 8px", fontSize: 10, cursor: "pointer",
                fontWeight: 500, transition: "all 0.15s"
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Filter tipe */}
        <select
          value={filters.violationType || ""}
          onChange={(e) => onFiltersChange({ ...filters, violationType: e.target.value || undefined })}
          style={{
            background: "rgb(var(--color-surface-container-low))", color: "rgb(var(--color-on-surface))", border: "1px solid rgb(var(--color-outline-variant))",
            borderRadius: 8, fontSize: 11, padding: "6px 10px", cursor: "pointer", outline: "none"
          }}
        >
          {VIOLATION_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
