import { useState } from "react";

export interface TaskItem {
  id: string;
  title: string;
  status: "In Progress" | "Pending" | "Completed";
  progress: number;
  etd?: string;
}

export interface TeamItem {
  id: string;
  name: string;
  type: string;
  status: "On Site" | "En Route" | "Standby";
  icon: string;
}

interface MitigationTasksPanelProps {
  tasks: TaskItem[];
  setTasks: React.Dispatch<React.SetStateAction<TaskItem[]>>;
  teams: TeamItem[];
  setTeams: React.Dispatch<React.SetStateAction<TeamItem[]>>;
  onClose: () => void;
  onActivityLog: (type: "incident" | "task" | "team", action: string, title: string, description: string, icon: string, color: string) => void;
}

export function MitigationTasksPanel({
  tasks,
  setTasks,
  teams,
  setTeams,
  onClose,
  onActivityLog
}: MitigationTasksPanelProps) {
  const [showForm, setShowForm] = useState(false);
  const [formTab, setFormTab] = useState<"task" | "team">("task");

  // Task Form State
  const [taskTitle, setTaskTitle] = useState("");
  const [taskStatus, setTaskStatus] = useState<"In Progress" | "Pending">("In Progress");
  const [taskProgress, setTaskProgress] = useState(50);
  const [taskEtd, setTaskEtd] = useState("");

  // Team Form State
  const [teamName, setTeamName] = useState("");
  const [teamType, setTeamType] = useState("Rapid Response");
  const [teamStatus, setTeamStatus] = useState<"On Site" | "En Route" | "Standby">("En Route");
  const [teamIcon, setTeamIcon] = useState("shield");

  const handleAddTask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskTitle.trim()) return;

    const newTask: TaskItem = {
      id: `task-${Date.now()}`,
      title: taskTitle.trim(),
      status: taskStatus === "In Progress" ? "In Progress" : "Pending",
      progress: taskStatus === "In Progress" ? taskProgress : 0,
      etd: taskStatus === "Pending" && taskEtd.trim() ? taskEtd.trim() : undefined,
    };

    setTasks((prev) => [newTask, ...prev]);
    onActivityLog(
      "task",
      "created",
      "Tugas Baru Dibuat",
      `Tugas "${newTask.title}" telah dibuat dengan status ${newTask.status}`,
      "playlist_add",
      "bg-primary/10 text-primary"
    );
    // Reset Form
    setTaskTitle("");
    setTaskProgress(50);
    setTaskEtd("");
    setShowForm(false);
  };

  const handleAddTeam = (e: React.FormEvent) => {
    e.preventDefault();
    if (!teamName.trim()) return;

    const newTeam: TeamItem = {
      id: `team-${Date.now()}`,
      name: teamName.trim(),
      type: teamType.trim(),
      status: teamStatus,
      icon: teamIcon,
    };

    setTeams((prev) => [newTeam, ...prev]);
    onActivityLog(
      "team",
      "deployed",
      "Unit Patroli Dikerahkan",
      `Unit ${newTeam.name} (${newTeam.type}) dikerahkan dengan status ${newTeam.status}`,
      "shield",
      "bg-teal-50 text-teal-700"
    );
    // Reset Form
    setTeamName("");
    setTeamType("Rapid Response");
    setTeamStatus("En Route");
    setTeamIcon("shield");
    setShowForm(false);
  };

  const toggleTaskStatus = (id: string) => {
    setTasks((prev) =>
      prev.map((t) => {
        if (t.id !== id) return t;
        let nextStatus: "In Progress" | "Pending" | "Completed" = "Pending";
        let nextProgress = 0;
        if (t.status === "Pending") {
          nextStatus = "In Progress";
          nextProgress = 50;
        } else if (t.status === "In Progress") {
          nextStatus = "Completed";
          nextProgress = 100;
        }
        
        onActivityLog(
          "task",
          "status_changed",
          "Status Tugas Diperbarui",
          `Tugas "${t.title}" diubah statusnya menjadi ${nextStatus}`,
          "playlist_add_check",
          "bg-indigo-50 text-indigo-700"
        );
        
        return { ...t, status: nextStatus, progress: nextProgress };
      })
    );
  };

  const handleProgressClick = (id: string, e: React.MouseEvent<HTMLDivElement>) => {
    e.stopPropagation();
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const width = rect.width;
    const newProgress = Math.min(100, Math.max(0, Math.round((clickX / width) * 100)));

    setTasks((prev) =>
      prev.map((t) => {
        if (t.id !== id) return t;
        const status = newProgress === 100 ? "Completed" : newProgress === 0 ? "Pending" : "In Progress";
        
        onActivityLog(
          "task",
          "progress_updated",
          "Progress Tugas Diubah",
          `Tugas "${t.title}" diperbarui progresnya menjadi ${newProgress}%`,
          "analytics",
          "bg-cyan-50 text-cyan-700"
        );
        
        return { ...t, progress: newProgress, status };
      })
    );
  };

  const toggleTeamStatus = (id: string) => {
    setTeams((prev) =>
      prev.map((t) => {
        if (t.id !== id) return t;
        let nextStatus: "On Site" | "En Route" | "Standby" = "Standby";
        if (t.status === "Standby") nextStatus = "En Route";
        else if (t.status === "En Route") nextStatus = "On Site";
        
        onActivityLog(
          "team",
          "status_changed",
          "Status Unit Diubah",
          `Unit "${t.name}" mengubah status pergerakan menjadi ${nextStatus}`,
          "local_shipping",
          "bg-orange-50 text-orange-700"
        );
        
        return { ...t, status: nextStatus };
      })
    );
  };

  const deleteTask = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setTasks((prev) => {
      const target = prev.find((t) => t.id === id);
      if (target) {
        onActivityLog(
          "task",
          "deleted",
          "Tugas Dihapus",
          `Tugas "${target.title}" telah dihapus`,
          "delete",
          "bg-rose-50 text-rose-700"
        );
      }
      return prev.filter((t) => t.id !== id);
    });
  };

  const deleteTeam = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setTeams((prev) => {
      const target = prev.find((t) => t.id === id);
      if (target) {
        onActivityLog(
          "team",
          "deleted",
          "Unit Ditarik",
          `Unit "${target.name}" telah ditarik dari tugas`,
          "person_remove",
          "bg-slate-100 text-slate-700"
        );
      }
      return prev.filter((t) => t.id !== id);
    });
  };

  return (
    <div className="flex-grow flex flex-col h-full overflow-hidden bg-white/50">
      {/* Header */}
      <div className="p-lg flex justify-between items-center border-b border-outline-variant bg-white/50 flex-shrink-0">
        <h2 className="font-headline-sm text-headline-sm text-on-surface tracking-wider uppercase">
          MITIGATION TASKS
        </h2>
        <button
          onClick={onClose}
          className="text-on-surface-variant/60 hover:text-on-surface transition-colors flex items-center justify-center p-1 rounded-full hover:bg-slate-100"
          title="Tutup Panel"
        >
          <span className="material-symbols-outlined text-[20px]">close</span>
        </button>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-lg space-y-lg">
        {showForm ? (
          /* Sleek Inline Add Form */
          <div className="bg-white/80 border border-outline-variant rounded-2xl p-md shadow-md space-y-md animate-in fade-in duration-200">
            <div className="flex border-b border-outline-variant pb-2">
              <button
                type="button"
                onClick={() => setFormTab("task")}
                className={`flex-1 text-[11px] font-bold uppercase tracking-wider pb-1 transition-colors ${
                  formTab === "task"
                    ? "text-primary border-b-2 border-primary"
                    : "text-on-surface-variant/60 hover:text-on-surface"
                }`}
              >
                Tugas Baru
              </button>
              <button
                type="button"
                onClick={() => setFormTab("team")}
                className={`flex-1 text-[11px] font-bold uppercase tracking-wider pb-1 transition-colors ${
                  formTab === "team"
                    ? "text-primary border-b-2 border-primary"
                    : "text-on-surface-variant/60 hover:text-on-surface"
                }`}
              >
                Unit Tim Baru
              </button>
            </div>

            {formTab === "task" ? (
              <form onSubmit={handleAddTask} className="space-y-sm">
                <div>
                  <label className="block text-[9px] font-bold text-on-surface-variant/80 uppercase mb-1">
                    Nama Tugas / Mitigasi
                  </label>
                  <input
                    type="text"
                    required
                    value={taskTitle}
                    onChange={(e) => setTaskTitle(e.target.value)}
                    placeholder="Contoh: Divert Jl. Sudirman"
                    className="w-full text-[12px] bg-slate-50 border border-outline-variant rounded-xl p-2 focus:outline-none focus:border-primary transition-colors text-on-surface"
                  />
                </div>

                <div className="grid grid-cols-2 gap-sm">
                  <div>
                    <label className="block text-[9px] font-bold text-on-surface-variant/80 uppercase mb-1">
                      Status Awal
                    </label>
                    <select
                      value={taskStatus}
                      onChange={(e) => setTaskStatus(e.target.value as any)}
                      className="w-full text-[12px] bg-slate-50 border border-outline-variant rounded-xl p-2 focus:outline-none focus:border-primary transition-colors text-on-surface"
                    >
                      <option value="In Progress">In Progress</option>
                      <option value="Pending">Pending</option>
                    </select>
                  </div>

                  {taskStatus === "Pending" ? (
                    <div>
                      <label className="block text-[9px] font-bold text-on-surface-variant/80 uppercase mb-1">
                        ETD (Waktu)
                      </label>
                      <input
                        type="text"
                        placeholder="Contoh: 14:30"
                        value={taskEtd}
                        onChange={(e) => setTaskEtd(e.target.value)}
                        className="w-full text-[12px] bg-slate-50 border border-outline-variant rounded-xl p-2 focus:outline-none focus:border-primary transition-colors text-on-surface"
                      />
                    </div>
                  ) : (
                    <div>
                      <label className="block text-[9px] font-bold text-on-surface-variant/80 uppercase mb-1">
                        Progress ({taskProgress}%)
                      </label>
                      <input
                        type="range"
                        min="0"
                        max="99"
                        value={taskProgress}
                        onChange={(e) => setTaskProgress(Number(e.target.value))}
                        className="w-full accent-primary h-8 cursor-pointer"
                      />
                    </div>
                  )}
                </div>

                <div className="flex gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowForm(false)}
                    className="flex-1 py-2 border border-outline-variant text-[11px] font-bold rounded-lg uppercase tracking-wider text-on-surface-variant hover:bg-slate-50 transition-colors"
                  >
                    Batal
                  </button>
                  <button
                    type="submit"
                    className="flex-1 py-2 bg-primary text-white text-[11px] font-bold rounded-lg uppercase tracking-wider hover:brightness-105 transition-colors"
                  >
                    Simpan
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleAddTeam} className="space-y-sm">
                <div className="grid grid-cols-2 gap-sm">
                  <div>
                    <label className="block text-[9px] font-bold text-on-surface-variant/80 uppercase mb-1">
                      Nama Unit
                    </label>
                    <input
                      type="text"
                      required
                      value={teamName}
                      onChange={(e) => setTeamName(e.target.value)}
                      placeholder="Contoh: Unit 05"
                      className="w-full text-[12px] bg-slate-50 border border-outline-variant rounded-xl p-2 focus:outline-none focus:border-primary transition-colors text-on-surface"
                    />
                  </div>

                  <div>
                    <label className="block text-[9px] font-bold text-on-surface-variant/80 uppercase mb-1">
                      Tipe Unit
                    </label>
                    <input
                      type="text"
                      required
                      value={teamType}
                      onChange={(e) => setTeamType(e.target.value)}
                      placeholder="Contoh: Traffic Control"
                      className="w-full text-[12px] bg-slate-50 border border-outline-variant rounded-xl p-2 focus:outline-none focus:border-primary transition-colors text-on-surface"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-sm">
                  <div>
                    <label className="block text-[9px] font-bold text-on-surface-variant/80 uppercase mb-1">
                      Status Awal
                    </label>
                    <select
                      value={teamStatus}
                      onChange={(e) => setTeamStatus(e.target.value as any)}
                      className="w-full text-[12px] bg-slate-50 border border-outline-variant rounded-xl p-2 focus:outline-none focus:border-primary transition-colors text-on-surface"
                    >
                      <option value="En Route">En Route</option>
                      <option value="On Site">On Site</option>
                      <option value="Standby">Standby</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[9px] font-bold text-on-surface-variant/80 uppercase mb-1">
                      Ikon Unit
                    </label>
                    <div className="grid grid-cols-4 gap-1 p-1 bg-slate-50 border border-outline-variant rounded-xl">
                      {["shield", "local_shipping", "airport_shuttle", "emergency"].map((icon) => (
                        <button
                          key={icon}
                          type="button"
                          onClick={() => setTeamIcon(icon)}
                          className={`material-symbols-outlined text-lg p-1.5 rounded-lg flex items-center justify-center transition-all ${
                            teamIcon === icon ? "bg-primary text-white scale-110 shadow-sm" : "text-on-surface-variant/60 hover:bg-slate-200"
                          }`}
                        >
                          {icon}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="flex gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowForm(false)}
                    className="flex-1 py-2 border border-outline-variant text-[11px] font-bold rounded-lg uppercase tracking-wider text-on-surface-variant hover:bg-slate-50 transition-colors"
                  >
                    Batal
                  </button>
                  <button
                    type="submit"
                    className="flex-1 py-2 bg-primary text-white text-[11px] font-bold rounded-lg uppercase tracking-wider hover:brightness-105 transition-colors"
                  >
                    Simpan
                  </button>
                </div>
              </form>
            )}
          </div>
        ) : (
          /* Normal view of tasks and assignments */
          <>
            {/* Active Tasks Section */}
            <section className="space-y-sm">
              <div className="flex items-center gap-xs mb-md">
                <span className="w-1 h-3 bg-primary-fixed-dim rounded-full"></span>
                <h3 className="font-label-xs text-label-xs uppercase text-on-surface-variant/80 font-bold">
                  Active Tasks
                </h3>
              </div>
              <div className="space-y-md">
                {tasks.length === 0 ? (
                  <p className="text-[11px] text-on-surface-variant/60 italic text-center py-4 bg-slate-50 rounded-xl border border-dashed border-outline-variant">
                    Tidak ada tugas mitigasi aktif
                  </p>
                ) : (
                  tasks.map((task) => (
                    <div
                      key={task.id}
                      className="group relative bg-surface-container-low p-md rounded-xl border border-outline-variant shadow-sm hover:shadow-md transition-all duration-200"
                    >
                      <div className="flex justify-between items-start mb-sm gap-2">
                        <span className="font-body-md text-body-md text-on-surface break-words flex-1">
                          {task.title}
                        </span>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleTaskStatus(task.id)}
                            className="text-left"
                            title="Klik untuk mengubah status"
                          >
                            {task.status === "In Progress" && (
                              <span className="text-[8px] bg-primary/10 text-primary px-2 py-0.5 rounded-full uppercase font-bold border border-primary/20 hover:bg-primary/20 transition-all cursor-pointer">
                                In Progress
                              </span>
                            )}
                            {task.status === "Pending" && (
                              <span className="text-[8px] bg-secondary-container/50 text-on-secondary-container px-2 py-0.5 rounded-full uppercase font-bold border border-outline-variant hover:bg-secondary-container transition-all cursor-pointer">
                                Pending
                              </span>
                            )}
                            {task.status === "Completed" && (
                              <span className="text-[8px] bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full uppercase font-bold border border-emerald-200 hover:bg-emerald-100 transition-all cursor-pointer">
                                Completed
                              </span>
                            )}
                          </button>
                          <button
                            onClick={(e) => deleteTask(task.id, e)}
                            className="text-on-surface-variant/40 hover:text-error transition-colors opacity-0 group-hover:opacity-100 p-0.5"
                            title="Hapus tugas"
                          >
                            <span className="material-symbols-outlined text-[16px]">delete</span>
                          </button>
                        </div>
                      </div>

                      {task.status === "Pending" ? (
                        <div className="flex items-center gap-xs text-on-surface-variant/60">
                          <span className="material-symbols-outlined text-[14px]">schedule</span>
                          <span className="text-[10px] font-medium">ETD: {task.etd || "Segera"}</span>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <div
                            onClick={(e) => handleProgressClick(task.id, e)}
                            className="relative mt-xs w-full bg-surface-container-high h-1.5 rounded-full overflow-hidden cursor-pointer"
                            title="Klik pada bar untuk mengatur progress secara presisi"
                          >
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                task.status === "Completed" ? "bg-emerald-500" : "bg-primary"
                              }`}
                              style={{ width: `${task.progress}%` }}
                            ></div>
                          </div>
                          <div className="flex justify-between items-center text-[8px] text-on-surface-variant/60">
                            <span>Mulai</span>
                            <span>{task.progress}% Selesai</span>
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* Team Assignment Section */}
            <section className="space-y-sm">
              <div className="flex items-center gap-xs mb-md">
                <span className="w-1 h-3 bg-secondary rounded-full"></span>
                <h3 className="font-label-xs text-label-xs uppercase text-on-surface-variant/80 font-bold">
                  Team Assignment
                </h3>
              </div>
              <div className="grid grid-cols-1 gap-sm">
                {teams.length === 0 ? (
                  <p className="text-[11px] text-on-surface-variant/60 italic text-center py-4 bg-slate-50 rounded-xl border border-dashed border-outline-variant">
                    Tidak ada unit tim terdeploy
                  </p>
                ) : (
                  teams.map((team) => (
                    <div
                      key={team.id}
                      className="group flex items-center justify-between p-md bg-white border border-outline-variant rounded-xl shadow-sm hover:shadow-md transition-all duration-200"
                    >
                      <div className="flex items-center gap-md">
                        <div
                          className={`w-8 h-8 rounded-full flex items-center justify-center ${
                            team.status === "On Site"
                              ? "bg-primary/10 text-primary"
                              : team.status === "En Route"
                              ? "bg-secondary-container text-secondary"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          <span className="material-symbols-outlined text-lg">{team.icon}</span>
                        </div>
                        <div>
                          <div className="font-body-md text-body-md text-on-surface font-semibold">{team.name}</div>
                          <div className="text-[9px] text-on-surface-variant/60 uppercase font-bold">
                            {team.type}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleTeamStatus(team.id)}
                          className="font-data-mono text-[10px] font-bold text-right transition-colors"
                          title="Klik untuk mengubah status tim"
                        >
                          {team.status === "On Site" && (
                            <span className="text-primary hover:text-primary/80">On Site</span>
                          )}
                          {team.status === "En Route" && (
                            <span className="text-secondary hover:text-secondary/80">En Route</span>
                          )}
                          {team.status === "Standby" && (
                            <span className="text-slate-500 hover:text-slate-700">Standby</span>
                          )}
                        </button>
                        <button
                          onClick={(e) => deleteTeam(team.id, e)}
                          className="text-on-surface-variant/40 hover:text-error transition-colors opacity-0 group-hover:opacity-100 p-0.5"
                          title="Hapus unit"
                        >
                          <span className="material-symbols-outlined text-[16px]">delete</span>
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>
          </>
        )}
      </div>

      {/* Panel Footer Action (Only shown when form is closed) */}
      {!showForm && (
        <div className="p-lg bg-white/50 border-t border-outline-variant flex-shrink-0">
          <button
            onClick={() => setShowForm(true)}
            className="w-full bg-primary text-white font-bold py-3 rounded-full flex items-center justify-center gap-sm hover:brightness-105 active:scale-95 transition-all shadow-md shadow-primary/20"
          >
            <span className="material-symbols-outlined text-[18px]">add</span>
            <span className="text-[12px] uppercase tracking-wider">New Task</span>
          </button>
        </div>
      )}
    </div>
  );
}
