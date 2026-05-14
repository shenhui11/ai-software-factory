import { FormEvent, type ReactNode, useEffect, useState } from "react";

import "./App.css";
import {
  type AuthSessionPayload,
  activateAdminMembershipPlan,
  adjustAdminQuota,
  changePassword,
  clearActiveTask,
  confirmChapter,
  createAdminMembershipPlan,
  createAdminOrder,
  createAdminUser,
  createProject,
  generateProjectFoundation,
  getProjectFoundationTask,
  createTask,
  getAdminUsers,
  deleteChapter,
  expandChapter,
  getAdminMemberships,
  getAdminOrders,
  getAdminSafetyPolicies,
  getAdminTaskLogs,
  getAdminGenres,
  getMe,
  getChapterDetail,
  deleteProject,
  listGenres,
  getProject,
  getQuotas,
  getTask,
  login,
  listProjects,
  logout,
  removeChapterParagraph,
  regenerateChapterDraft,
  regenerateChapterOutlines,
  register,
  resetAdminUserPassword,
  rewriteChapter,
  runTask,
  selectOutlineOption,
  updateChapter,
  updateChapterDraft,
  updateAdminMembershipPlan,
  updateAdminOrder,
  updateAdminSafetyPolicy,
  updateAdminGenre,
  updateOutlineOption,
} from "./api";
import {
  genreLabels,
  initialForm,
  labels,
  lengthLabels,
  modeLabels,
  statusLabels,
  templateStatusLabel,
  translateLabel,
  type Mode,
  type ProjectForm,
} from "./i18n";

type Route =
  | "/login"
  | "/projects"
  | "/projects/detail"
  | "/projects/chapter"
  | "/account/security"
  | "/admin/users"
  | "/admin/memberships"
  | "/admin/orders"
  | "/admin/genres"
  | "/admin/safety"
  | "/admin/logs";

type AuthMode = "login" | "register";

type Session = AuthSessionPayload;

type OutlineEdit = {
  content: string;
  core_conflict: string;
  key_event: string;
  ending_hook: string;
};

type PlanForm = {
  name: string;
  daily_free_chapters: number;
  monthly_free_chapters: number;
  description: string;
};

type OrderForm = {
  plan_id: string;
  amount: number;
  status: string;
  note: string;
};

type AdminUserForm = {
  username: string;
};

type GenreAdminForm = {
  value: string;
  label: string;
  required_any: string;
  forbidden_any: string;
};

type ChapterTransformResult = {
  original: string;
  updated: string;
  diff: Array<{ type: string; text: string }>;
  consistency_note: string;
  chapter_updated: string | null;
};

type ChapterFeedback = {
  tone: "working" | "success" | "error";
  message: string;
};

type NextChapterReadyNotice = {
  chapterId: string;
  chapterIndex: number;
  taskId: string;
};

type PasswordForm = {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
};

const SESSION_STORAGE_KEY = "novel-workshop-session";
const WORKSPACE_STORAGE_KEY = "novel-workshop-workspace";
const FOUNDATION_BUSY_STORAGE_KEY = "novel-workshop-foundation-busy";
const FOUNDATION_TASK_STORAGE_KEY = "novel-workshop-foundation-task-id";
const defaultCreatorRoute: Route = "/projects";
const defaultAdminRoute: Route = "/admin/users";

const initialPlanForm: PlanForm = {
  name: "进阶套餐",
  daily_free_chapters: 10,
  monthly_free_chapters: 50,
  description: "适合持续连载项目。",
};

const initialOrderForm: OrderForm = {
  plan_id: "plan-basic",
  amount: 19.9,
  status: "待支付",
  note: "后台新增测试订单",
};

const initialAdminUserForm: AdminUserForm = {
  username: "",
};

const initialGenreAdminForm: GenreAdminForm = {
  value: "",
  label: "",
  required_any: "",
  forbidden_any: "",
};

const initialPasswordForm: PasswordForm = {
  currentPassword: "",
  newPassword: "",
  confirmPassword: "",
};

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildOutlineEdit(option: any): OutlineEdit {
  return {
    content: option.content,
    core_conflict: option.core_conflict,
    key_event: option.key_event,
    ending_hook: option.ending_hook,
  };
}

function storyBeatsToText(storyBeats: Array<Record<string, any>>) {
  return storyBeats
    .map((item, index) => {
      const phaseIndex = item.phase_index ?? index + 1;
      const label = item.label ?? `阶段 ${phaseIndex}`;
      const chapterRange = `${item.target_chapter_start ?? "?"}-${item.target_chapter_end ?? "?"}`;
      return [
        `阶段 ${phaseIndex}`,
        label,
        chapterRange,
        item.phase_goal ?? "",
        (item.phase_pressure ?? []).join("；"),
        (item.required_change ?? []).join("；"),
        (item.forbidden_outcomes ?? []).join("；"),
        (item.foreshadow_to_surface ?? []).join("；"),
        item.tone_trend ?? "",
        (item.flex_points ?? []).join("；"),
      ].join("｜");
    })
    .join("\n");
}

function parseStoryBeatsInput(value: string) {
  return splitLines(value).map((line, index) => {
    const [phaseToken, label, chapterRange, phaseGoal, phasePressure, requiredChange, forbiddenOutcomes, foreshadowToSurface, toneTrend, flexPoints] =
      line.split("｜").map((item) => item.trim());
    const phaseIndexMatch = phaseToken?.match(/\d+/);
    const [startRaw, endRaw] = (chapterRange ?? "").split("-").map((item) => item.trim());
    return {
      phase_index: Number(phaseIndexMatch?.[0] ?? index + 1),
      label: label || `阶段 ${index + 1}`,
      target_chapter_start: Number(startRaw || index * 3 + 1),
      target_chapter_end: Number(endRaw || index * 3 + 3),
      phase_goal: phaseGoal || "",
      phase_pressure: phasePressure ? phasePressure.split("；").map((item) => item.trim()).filter(Boolean) : [],
      required_change: requiredChange ? requiredChange.split("；").map((item) => item.trim()).filter(Boolean) : [],
      forbidden_outcomes: forbiddenOutcomes ? forbiddenOutcomes.split("；").map((item) => item.trim()).filter(Boolean) : [],
      foreshadow_to_surface: foreshadowToSurface ? foreshadowToSurface.split("；").map((item) => item.trim()).filter(Boolean) : [],
      tone_trend: toneTrend || "",
      flex_points: flexPoints ? flexPoints.split("；").map((item) => item.trim()).filter(Boolean) : [],
    };
  });
}

function extractPhaseSignalTerms(values: string[]) {
  const seen = new Set<string>();
  const terms: string[] = [];
  values.forEach((value) => {
    value
      .split(/[，。；：、\s/|（）()\-]+/)
      .map((item) => item.trim())
      .filter((item) => item.length >= 2 && item.length <= 16)
      .forEach((item) => {
        if (!seen.has(item)) {
          seen.add(item);
          terms.push(item);
        }
      });
  });
  return terms.slice(0, 16);
}

function scoreOutlineAgainstPhase(option: any, activePhase: any) {
  if (!activePhase || Object.keys(activePhase).length === 0) {
    return { label: "暂无阶段参照", tone: "neutral", hits: [] as string[] };
  }
  const phaseTerms = extractPhaseSignalTerms([
    activePhase.phase_goal ?? "",
    ...(activePhase.phase_pressure ?? []),
    ...(activePhase.required_change ?? []),
    ...(activePhase.foreshadow_to_surface ?? []),
  ]);
  const optionText = [option.content, option.core_conflict, option.key_event, option.ending_hook].join(" ");
  const hits = phaseTerms.filter((term) => optionText.includes(term)).slice(0, 4);
  if (hits.length >= 3) {
    return { label: "阶段贴合度高", tone: "strong", hits };
  }
  if (hits.length >= 1) {
    return { label: "阶段贴合度中", tone: "medium", hits };
  }
  return { label: "阶段贴合度弱", tone: "weak", hits: [] as string[] };
}

function buildTaskRelayItems(taskData: any) {
  const task = taskData?.task;
  if (!task) {
    return [];
  }
  const start = Number(task.start_chapter_index ?? 1);
  const count = Number(task.requested_chapter_count ?? 0);
  const current = Number(task.current_chapter_index ?? start);
  const chapters = Array.isArray(taskData?.chapters) ? taskData.chapters : [];
  return Array.from({ length: count }, (_, offset) => {
    const chapterIndex = start + offset;
    const chapter = chapters.find((item: any) => item.chapter_index === chapterIndex);
    if (chapter?.confirmed_by_user) {
      return { chapterIndex, tone: "confirmed", label: "已确认", chapterId: chapter.id };
    }
    if (chapter && task.status === "waiting_user_confirm" && !chapter.confirmed_by_user) {
      return { chapterIndex, tone: "ready", label: "待确认", chapterId: chapter.id };
    }
    if (chapter && current > chapterIndex) {
      return { chapterIndex, tone: "generated", label: "已生成", chapterId: chapter.id };
    }
    if (current === chapterIndex && ["queued", "running"].includes(task.status)) {
      return { chapterIndex, tone: "working", label: "生成中", chapterId: chapter?.id ?? "" };
    }
    return { chapterIndex, tone: "pending", label: "待生成", chapterId: chapter?.id ?? "" };
  });
}

function translateGenre(value: string, genres: Array<{ value: string; label: string }>) {
  return genreLabels[value] ?? genres.find((item) => item.value === value)?.label ?? value;
}

function ensureGenreOptions(genres: Array<{ value: string; label: string }>, currentValue: string) {
  if (!currentValue || genres.some((item) => item.value === currentValue)) {
    return genres;
  }
  return [...genres, { value: currentValue, label: currentValue }];
}

function maskUsername(username: string) {
  const value = username.trim();
  if (value.length <= 1) {
    return "*";
  }
  if (value.length === 2) {
    return `${value[0]}*`;
  }
  return `${value.slice(0, 2)}***${value.slice(-1)}`;
}

function readRoute(): Route {
  const hash = window.location.hash.replace(/^#/, "");
  const allowedRoutes: Route[] = [
    "/login",
    "/projects",
    "/projects/detail",
    "/projects/chapter",
    "/account/security",
    "/admin/users",
    "/admin/memberships",
    "/admin/orders",
    "/admin/genres",
    "/admin/safety",
    "/admin/logs",
  ];
  return allowedRoutes.includes(hash as Route) ? (hash as Route) : "/login";
}

function writeRoute(route: Route) {
  window.location.hash = route;
}

function readSession(): Session | null {
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Session;
    if (parsed?.token && parsed.user?.username && (parsed.user.role === "creator" || parsed.user.role === "admin")) {
      return parsed;
    }
  } catch {
    return null;
  }
  return null;
}

function persistSession(session: Session | null) {
  if (!session) {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
}

function currentRouteForSession(session: Session) {
  return session.user.role === "admin" ? defaultAdminRoute : defaultCreatorRoute;
}

function isAdminRoute(route: Route) {
  return route.startsWith("/admin");
}

function isSharedRoute(route: Route) {
  return route === "/account/security";
}

function isCreatorRoute(route: Route) {
  return route === "/projects" || route === "/projects/detail" || route === "/projects/chapter";
}

type WorkspaceState = {
  selectedProjectId: string;
  selectedTaskId: string;
  selectedChapterId: string;
};

const initialWorkspaceState: WorkspaceState = {
  selectedProjectId: "",
  selectedTaskId: "",
  selectedChapterId: "",
};

function readWorkspaceState(): WorkspaceState {
  const raw = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
  if (!raw) {
    return initialWorkspaceState;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<WorkspaceState>;
    return {
      selectedProjectId: parsed.selectedProjectId ?? "",
      selectedTaskId: parsed.selectedTaskId ?? "",
      selectedChapterId: parsed.selectedChapterId ?? "",
    };
  } catch {
    return initialWorkspaceState;
  }
}

function persistWorkspaceState(workspace: WorkspaceState) {
  if (!workspace.selectedProjectId && !workspace.selectedTaskId && !workspace.selectedChapterId) {
    window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(workspace));
}

function readFoundationBusyMessage() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.sessionStorage.getItem(FOUNDATION_BUSY_STORAGE_KEY) ?? "";
}

function persistFoundationBusyMessage(message: string) {
  if (typeof window === "undefined") {
    return;
  }
  if (!message) {
    window.sessionStorage.removeItem(FOUNDATION_BUSY_STORAGE_KEY);
    return;
  }
  window.sessionStorage.setItem(FOUNDATION_BUSY_STORAGE_KEY, message);
}

function readFoundationTaskId() {
  if (typeof window === "undefined") {
    return "";
  }
  return window.sessionStorage.getItem(FOUNDATION_TASK_STORAGE_KEY) ?? "";
}

function persistFoundationTaskId(taskId: string) {
  if (typeof window === "undefined") {
    return;
  }
  if (!taskId) {
    window.sessionStorage.removeItem(FOUNDATION_TASK_STORAGE_KEY);
    return;
  }
  window.sessionStorage.setItem(FOUNDATION_TASK_STORAGE_KEY, taskId);
}

function AccountSecurityPage(props: {
  passwordForm: PasswordForm;
  loading: boolean;
  onPasswordFormChange: (value: PasswordForm) => void;
  onPasswordSubmit: (event: FormEvent) => void;
}) {
  return (
    <section className="panel">
      <div className="section-title-row">
        <div>
          <span className="eyebrow">Security</span>
          <h2>账号安全</h2>
        </div>
        <span className="hint-text">修改密码后，旧登录会话会自动失效。</span>
      </div>
      <form onSubmit={props.onPasswordSubmit} className="form-grid">
        <label>
          当前密码
          <input
            type="password"
            value={props.passwordForm.currentPassword}
            onChange={(event) => props.onPasswordFormChange({ ...props.passwordForm, currentPassword: event.target.value })}
          />
        </label>
        <label>
          新密码
          <input
            type="password"
            value={props.passwordForm.newPassword}
            onChange={(event) => props.onPasswordFormChange({ ...props.passwordForm, newPassword: event.target.value })}
          />
        </label>
        <label>
          确认新密码
          <input
            type="password"
            value={props.passwordForm.confirmPassword}
            onChange={(event) => props.onPasswordFormChange({ ...props.passwordForm, confirmPassword: event.target.value })}
          />
        </label>
        <div className="inline">
          <button type="submit" disabled={props.loading}>
            {props.loading ? labels.states.working : "修改密码"}
          </button>
        </div>
      </form>
    </section>
  );
}

function BusyOverlay(props: { visible: boolean; title: string; detail: string; elapsedSeconds: number }) {
  if (!props.visible) {
    return null;
  }
  const delayed = props.elapsedSeconds >= 15;
  return (
    <div className="busy-overlay" role="status" aria-live="polite" aria-busy="true">
      <div className="busy-overlay-card">
        <div className="busy-spinner" aria-hidden="true" />
        <span className="busy-overlay-eyebrow">系统处理中</span>
        <h2>{props.title}</h2>
        <p>{props.detail}</p>
        <div className="busy-overlay-meta">
          <strong>已等待 {props.elapsedSeconds} 秒</strong>
          <span>
            {delayed ? "模型响应较慢属于正常情况，系统仍在持续处理，请继续等待。" : "页面未卡住，系统仍在执行，请不要重复点击或刷新页面。"}
          </span>
        </div>
      </div>
    </div>
  );
}

function LoginPage(props: {
  mode: AuthMode;
  username: string;
  password: string;
  confirmPassword: string;
  loading: boolean;
  error: string;
  onModeChange: (value: AuthMode) => void;
  onUsernameChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onConfirmPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const isRegister = props.mode === "register";
  return (
    <div className="auth-shell">
      <section className="auth-card panel">
        <div className="auth-brand">
          <span className="auth-brand-badge">Novel Workshop</span>
          <h1>{labels.appTitle}</h1>
          <p>{labels.appSubtitle}</p>
        </div>
        <div className="auth-segmented">
          <button type="button" className={props.mode === "login" ? "nav-link nav-link-active" : "nav-link"} onClick={() => props.onModeChange("login")}>
            登录
          </button>
          {/* <button
            type="button"
            className={props.mode === "register" ? "nav-link nav-link-active" : "nav-link"}
            onClick={() => props.onModeChange("register")}
          >
            注册
          </button> */}
        </div>
        <form onSubmit={props.onSubmit} className="form-grid">
          <label>
            用户名
            <input value={props.username} onChange={(event) => props.onUsernameChange(event.target.value)} placeholder="请输入用户名" />
          </label>
          <label>
            密码
            <input type="password" value={props.password} onChange={(event) => props.onPasswordChange(event.target.value)} placeholder="至少 6 位" />
          </label>
          {isRegister ? (
            <>
              <label>
                确认密码
                <input
                  type="password"
                  value={props.confirmPassword}
                  onChange={(event) => props.onConfirmPasswordChange(event.target.value)}
                  placeholder="再次输入密码"
                />
              </label>
            </>
          ) : null}
          <button type="submit" disabled={props.loading}>
            {props.loading ? labels.states.working : isRegister ? "注册并进入系统" : "登录进入系统"}
          </button>
        </form>
        <div className="auth-footnote">
          <p className="hint-text">公开注册默认创建创作者账号；管理员账号仅允许后台单独维护。</p>
        </div>
        {props.error ? <div className="error">{props.error}</div> : null}
      </section>
    </div>
  );
}

function AppShell(props: {
  title: string;
  subtitle: string;
  session: Session;
  route: Route;
  navItems: Array<{ route: Route; label: string }>;
  onNavigate: (route: Route) => void;
  onLogout: () => void;
  passwordForm: PasswordForm;
  passwordLoading: boolean;
  onPasswordFormChange: (value: PasswordForm) => void;
  onPasswordSubmit: (event: FormEvent) => void;
  children: ReactNode;
}) {
  return (
    <div className="shell">
      <header className="app-header panel">
        <div className="app-header-main">
          <div className="app-mark">NW</div>
          <div>
            <span className="eyebrow">AI Novel Studio</span>
            <h1>{props.title}</h1>
            <p>{props.subtitle}</p>
          </div>
        </div>
        <div className="header-meta">
          {/* <h1>{props.title}</h1> */}
          <div>
            <strong>{maskUsername(props.session.user.username)}</strong>
            <span>{props.session.user.role === "admin" ? "管理员" : "创作者"}</span>
          </div>
          <button onClick={props.onLogout}>退出登录</button>
        </div>
      </header>

      <div className="app-layout">
        <aside className="side-nav panel">
          <div className="side-nav-section-label">工作区导航</div>
          {props.navItems.map((item) => (
            <button
              key={item.route}
              className={props.route === item.route ? "nav-link nav-link-active" : "nav-link"}
              onClick={() => props.onNavigate(item.route)}
            >
              {item.label}
            </button>
          ))}
        </aside>
        <main className="content-stack">{props.children}</main>
      </div>
    </div>
  );
}

function ProjectSetupPanel(props: {
  form: ProjectForm;
  genres: Array<{ value: string; label: string }>;
  loading: boolean;
  onChange: (value: ProjectForm) => void;
  onGenerateFoundation: () => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const [genreMenuOpen, setGenreMenuOpen] = useState(false);

  function toggleGenre(value: string, checked: boolean) {
    const nextGenres = checked
      ? Array.from(new Set([...props.form.genres, value]))
      : props.form.genres.filter((item) => item !== value);
    const resolvedGenres = nextGenres.length ? nextGenres : [value];
    props.onChange({ ...props.form, genres: resolvedGenres, genre: resolvedGenres[0] });
  }

  const selectedGenreLabels = props.form.genres.map((value) => translateGenre(value, props.genres));
  const genreTriggerText =
    selectedGenreLabels.length === 0
      ? "请选择题材"
      : selectedGenreLabels.length <= 2
        ? selectedGenreLabels.join(" / ")
        : `${selectedGenreLabels.slice(0, 2).join(" / ")} +${selectedGenreLabels.length - 2}`;

  return (
    <section className="panel">
      <div className="section-title-row">
        <div>
          <span className="eyebrow">Project Setup</span>
          <h2>项目创建</h2>
        </div>
      </div>
      <form onSubmit={props.onSubmit} className="form-grid">
        <label>
          {labels.fields.title}
          <input value={props.form.title} onChange={(event) => props.onChange({ ...props.form, title: event.target.value })} />
        </label>
        <label>
          {labels.fields.genre}
          <div className="multi-select">
            <button
              type="button"
              className="multi-select-trigger"
              onClick={() => setGenreMenuOpen((current) => !current)}
            >
              <span>{genreTriggerText}</span>
              <span>{genreMenuOpen ? "收起" : "展开"}</span>
            </button>
            {genreMenuOpen ? (
              <div className="multi-select-menu">
                {props.genres.map((genre) => (
                  <label key={genre.value} className="checkbox-item">
                    <input
                      type="checkbox"
                      checked={props.form.genres.includes(genre.value)}
                      onChange={(event) => toggleGenre(genre.value, event.target.checked)}
                    />
                    <span>{translateGenre(genre.value, props.genres)}</span>
                  </label>
                ))}
              </div>
            ) : null}
          </div>
        </label>
        <label>
          {labels.fields.lengthType}
          <select value={props.form.length_type} onChange={(event) => props.onChange({ ...props.form, length_type: event.target.value })}>
            <option value="long">{lengthLabels.long}</option>
            <option value="short">{lengthLabels.short}</option>
          </select>
        </label>
        <label className="full">
          {labels.fields.summary}
          <textarea value={props.form.summary} onChange={(event) => props.onChange({ ...props.form, summary: event.target.value })} rows={4} />
        </label>
        <label>
          {labels.fields.characterCards}
          <textarea value={props.form.character_cards} onChange={(event) => props.onChange({ ...props.form, character_cards: event.target.value })} rows={4} />
        </label>
        <label>
          {labels.fields.worldRules}
          <textarea value={props.form.world_rules} onChange={(event) => props.onChange({ ...props.form, world_rules: event.target.value })} rows={4} />
        </label>
        <label>
          {labels.fields.eventSummary}
          <textarea value={props.form.event_summary} onChange={(event) => props.onChange({ ...props.form, event_summary: event.target.value })} rows={4} />
        </label>
        <label className="full">
          {labels.fields.storyBeats}
          <textarea
            value={props.form.story_beats}
            onChange={(event) => props.onChange({ ...props.form, story_beats: event.target.value })}
            rows={6}
          />
          <span className="hint-text">格式：阶段序号｜阶段名｜起止章节｜阶段目标｜阶段压力｜必须变化｜禁止结果｜浮现伏笔｜情绪趋势｜自由发挥区</span>
        </label>
        <label>
          {labels.fields.defaultMode}
          <select value={props.form.mode_default} onChange={(event) => props.onChange({ ...props.form, mode_default: event.target.value as Mode })}>
            <option value="manual">{modeLabels.manual}</option>
            <option value="auto">{modeLabels.auto}</option>
          </select>
        </label>
        <div className="inline full">
          <button type="button" onClick={props.onGenerateFoundation} disabled={props.loading || !props.form.title.trim()}>
            {props.loading ? labels.states.working : labels.actions.generateFoundation}
          </button>
          <button type="submit" disabled={props.loading}>
            {props.loading ? labels.states.working : labels.actions.createProject}
          </button>
        </div>
      </form>
    </section>
  );
}

function ProjectListPage(props: {
  projects: any[];
  genres?: Array<{ value: string; label: string }>;
  selectedProjectId: string;
  loading: boolean;
  onOpenProject: (projectId: string) => void;
  onDeleteProject: (project: any) => void;
}) {
  return (
    <section className="panel">
      <div className="section-title-row">
        <div>
          <span className="eyebrow">Projects</span>
          <h2>项目列表</h2>
        </div>
        <span className="hint-text">先选项目，再进入章节生产与审稿流程。</span>
      </div>
      {props.projects.length ? (
        <div className="log-list">
          {props.projects.map((project) => (
            <div key={project.id} className={props.selectedProjectId === project.id ? "selected card" : "card"}>
              <div className="section-title-row">
                <div>
                  <strong>{project.title}</strong>
                  <div>{translateGenre(project.genre, props.genres ?? [])} / {translateLabel(project.length_type, lengthLabels)}</div>
                </div>
                <div className="inline">
                  <button onClick={() => props.onOpenProject(project.id)} disabled={props.loading}>打开项目</button>
                  <button type="button" className="danger-button" onClick={() => props.onDeleteProject(project)} disabled={props.loading}>
                    删除项目
                  </button>
                </div>
              </div>
              <div>{project.summary}</div>
              <div className="hint-text">章节数：{project.chapters?.length ?? 0}，任务数：{project.tasks?.length ?? 0}</div>
            </div>
          ))}
        </div>
      ) : (
        <p>{labels.states.noProject} 暂无项目。</p>
      )}
    </section>
  );
}

function ProjectDetailPage(props: {
  projectData: any;
  taskData: any;
  quotaData: any;
  genres: Array<{ value: string; label: string }>;
  taskMode: Mode;
  chapterCount: number;
  loading: boolean;
  runningTask: boolean;
  hasActiveTask: boolean;
  onModeChange: (value: Mode) => void;
  onChapterCountChange: (value: number) => void;
  onRunTask: () => void;
  onClearActiveTask: () => void;
  onOpenChapter: (chapterId: string) => void;
  onDeleteProject: (project: any) => void;
}) {
  const [memoryExpanded, setMemoryExpanded] = useState(false);
  const [projectContextExpanded, setProjectContextExpanded] = useState(false);
  const taskStatus = props.taskData?.task?.status ?? "";
  const isTaskActive = ["queued", "running", "waiting_user_confirm"].includes(taskStatus);
  const currentTaskChapters = props.taskData?.chapters ?? [];
  const allProjectChapters = props.projectData?.project?.chapters ?? [];

  return (
    <>
      <div className="project-workbench">
        <section className="panel project-overview-panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Project Overview</span>
              <h2>项目概览</h2>
            </div>
            {props.projectData ? (
              <div className="inline">
                <span className="hint-text">围绕章节连续生产组织项目信息。</span>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => props.onDeleteProject(props.projectData.project)}
                  disabled={props.loading}
                >
                  删除项目
                </button>
              </div>
            ) : null}
          </div>
          {props.projectData ? (
            <>
              <div className="project-hero">
                <div>
                  <span className="project-hero-tag">{translateGenre(props.projectData.project.genre, props.genres)}</span>
                  <h3>{props.projectData.project.title}</h3>
                  <p>{props.projectData.project.summary}</p>
                </div>
              </div>
              <div className="project-kpi-grid">
                <div className="summary-box">
                  <span className="summary-label">项目名</span>
                  <strong>{props.projectData.project.title}</strong>
                </div>
                <div className="summary-box">
                  <span className="summary-label">题材</span>
                  <strong>{translateGenre(props.projectData.project.genre, props.genres)}</strong>
                </div>
                <div className="summary-box">
                  <span className="summary-label">默认模式</span>
                  <strong>{translateLabel(props.projectData.project.mode_default, modeLabels)}</strong>
                </div>
                <div className="summary-box">
                  <span className="summary-label">已生成章节</span>
                  <strong>{props.projectData.project.chapters?.length ?? 0}</strong>
                </div>
              </div>
              <div className="section-title-row">
                <div>
                  <span className="eyebrow">Project Context</span>
                  <h3>项目设定</h3>
                </div>
                <button type="button" className="ghost-button" onClick={() => setProjectContextExpanded((current) => !current)}>
                  {projectContextExpanded ? "收起" : "展开"}
                </button>
              </div>
              {projectContextExpanded ? (
                <>
                  <div className="project-copy-block">
                    <strong>角色卡</strong>
                    <p>{(props.projectData.project.memory?.character_cards ?? []).join(" / ") || "暂无"}</p>
                  </div>
                  <div className="project-copy-block">
                    <strong>世界规则</strong>
                    <p>{(props.projectData.project.memory?.world_rules ?? []).join(" / ") || "暂无"}</p>
                  </div>
                </>
              ) : (
                <p className="hint-text">角色卡和世界规则已折叠。</p>
              )}
            </>
          ) : (
            <p>请选择一个项目。</p>
          )}
        </section>

        <div className="project-side-column">
          <TaskControlPanel
            projectData={props.projectData}
            quotaData={props.quotaData}
            taskData={props.taskData}
            taskMode={props.taskMode}
            chapterCount={props.chapterCount}
            loading={props.loading}
            runningTask={props.runningTask}
            hasActiveTask={props.hasActiveTask}
            onModeChange={props.onModeChange}
            onChapterCountChange={props.onChapterCountChange}
            onRunTask={props.onRunTask}
            onClearActiveTask={props.onClearActiveTask}
            onOpenChapter={props.onOpenChapter}
          />

          <section className="panel">
            <div className="section-title-row">
              <div>
                <span className="eyebrow">Memory</span>
                <h2>结构化记忆</h2>
              </div>
              {props.taskData?.memory ? (
                <button type="button" className="ghost-button" onClick={() => setMemoryExpanded((current) => !current)}>
                  {memoryExpanded ? "收起" : "展开"}
                </button>
              ) : null}
            </div>
            {props.taskData?.memory ? (
              <div className="memory-stack">
                <div className="memory-summary-grid">
                  <div className="summary-box">
                    <span className="summary-label">角色卡</span>
                    <strong>{(props.taskData.memory.character_cards ?? []).length} 条</strong>
                  </div>
                  <div className="summary-box">
                    <span className="summary-label">角色状态</span>
                    <strong>{props.taskData.memory.character_profiles?.length ?? 0} 条</strong>
                  </div>
                  <div className="summary-box">
                    <span className="summary-label">关系状态</span>
                    <strong>{props.taskData.memory.relationship_states?.length ?? 0} 条</strong>
                  </div>
                  <div className="summary-box">
                    <span className="summary-label">世界规则</span>
                    <strong>{(props.taskData.memory.world_rules ?? []).length} 条</strong>
                  </div>
                </div>
                {memoryExpanded ? (
                  <>
                    <div className="project-copy-block">
                      <strong>当前阶段</strong>
                      {props.taskData.memory.active_phase && Object.keys(props.taskData.memory.active_phase).length > 0 ? (
                        <div className="phase-highlight-card">
                          <div className="phase-highlight-meta">
                            <span className="phase-chip">Phase {props.taskData.memory.active_phase.phase_index ?? "-"}</span>
                            <span className="phase-status">{props.taskData.memory.active_phase.status ?? "active"}</span>
                          </div>
                          <h4>{props.taskData.memory.active_phase.label ?? "当前阶段"}</h4>
                          <p>{props.taskData.memory.active_phase.phase_goal ?? "暂无阶段目标"}</p>
                          <div className="phase-mini-grid">
                            <div>
                              <span className="summary-label">阶段压力</span>
                              <p>{(props.taskData.memory.active_phase.phase_pressure ?? []).join(" / ") || "暂无"}</p>
                            </div>
                            <div>
                              <span className="summary-label">必须变化</span>
                              <p>{(props.taskData.memory.active_phase.required_change ?? []).join(" / ") || "暂无"}</p>
                            </div>
                            <div>
                              <span className="summary-label">禁止结果</span>
                              <p>{(props.taskData.memory.active_phase.forbidden_outcomes ?? []).join(" / ") || "暂无"}</p>
                            </div>
                            <div>
                              <span className="summary-label">可自由发挥</span>
                              <p>{(props.taskData.memory.active_phase.flex_points ?? []).join(" / ") || "暂无"}</p>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <p>暂无</p>
                      )}
                    </div>
                    <div className="project-copy-block">
                      <strong>阶段节拍</strong>
                      {(props.taskData.memory.story_beats ?? []).length ? (
                        <div className="phase-beat-list">
                          {(props.taskData.memory.story_beats ?? []).map((item: any) => (
                            <div
                              key={`beat-${item.phase_index}-${item.label}`}
                              className={`phase-beat-card ${item.status === "active" ? "phase-beat-card-active" : ""}`}
                            >
                              <div className="phase-highlight-meta">
                                <span className="phase-chip">Phase {item.phase_index ?? "-"}</span>
                                <span className="phase-status">{item.status ?? "pending"}</span>
                              </div>
                              <h4>{item.label ?? "未命名阶段"}</h4>
                              <p>{item.phase_goal ?? "暂无阶段目标"}</p>
                              <div className="phase-beat-range">
                                目标章节：第 {item.target_chapter_start ?? "?"} 章 - 第 {item.target_chapter_end ?? "?"} 章
                              </div>
                              <div className="phase-mini-grid">
                                <div>
                                  <span className="summary-label">变化方向</span>
                                  <p>{(item.required_change ?? []).join(" / ") || "暂无"}</p>
                                </div>
                                <div>
                                  <span className="summary-label">浮现伏笔</span>
                                  <p>{(item.foreshadow_to_surface ?? []).join(" / ") || "暂无"}</p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p>暂无</p>
                      )}
                    </div>
                    <div className="project-copy-block">
                      <strong>角色卡</strong>
                      <p>{(props.taskData.memory.character_cards ?? []).join(" / ") || "暂无"}</p>
                    </div>
                    <div className="project-copy-block">
                      <strong>世界规则</strong>
                      <p>{(props.taskData.memory.world_rules ?? []).join(" / ") || "暂无"}</p>
                    </div>
                    <div className="project-copy-block">
                      <strong>事件摘要</strong>
                      <p>{(props.taskData.memory.event_summary ?? []).join("；") || "暂无"}</p>
                    </div>
                    <div className="project-copy-block">
                      <strong>角色档案</strong>
                      <p>
                        {(props.taskData.memory.character_profiles ?? [])
                          .map((item: any) => `${item.name}：${item.current_state ?? "暂无状态"}；目标 ${item.current_goal ?? "暂无"}`)
                          .join("\n") || "暂无"}
                      </p>
                    </div>
                    <div className="project-copy-block">
                      <strong>关系状态</strong>
                      <p>
                        {(props.taskData.memory.relationship_states ?? [])
                          .map((item: any) => `${item.source} - ${item.target}：${item.status}（第 ${item.chapter_index} 章）`)
                          .join("\n") || "暂无"}
                      </p>
                    </div>
                    <div className="project-copy-block">
                      <strong>章节摘要</strong>
                      <p>
                        {(props.taskData.memory.chapter_summaries ?? [])
                          .map((item: any) => `第 ${item.chapter_index} 章：${item.summary}`)
                          .join("\n") || "暂无"}
                      </p>
                    </div>
                    <div className="project-copy-block">
                      <strong>时间线</strong>
                      <p>
                        {(props.taskData.memory.timeline_nodes ?? [])
                          .map((item: any) => `第 ${item.chapter_index} 章：${item.summary}`)
                          .join("\n") || "暂无"}
                      </p>
                    </div>
                    <div className="project-copy-block">
                      <strong>重大事件</strong>
                      <p>
                        {(props.taskData.memory.major_events ?? [])
                          .map((item: any) => `第 ${item.chapter_index} 章：${item.summary} / 影响：${item.impact}`)
                          .join("\n") || "暂无"}
                      </p>
                    </div>
                    <div className="project-copy-block">
                      <strong>伏笔 / 坑点</strong>
                      <p>
                        {(props.taskData.memory.foreshadow_threads ?? [])
                          .map((item: any) => `${item.title}：${item.latest_progress_note}（${item.status}）`)
                          .join("\n") || "暂无"}
                      </p>
                    </div>
                    <div className="project-copy-block">
                      <strong>事实记录</strong>
                      <p>
                        {(props.taskData.memory.fact_records ?? [])
                          .map((item: any) => `第 ${item.chapter_index} 章 / ${item.fact_type} / ${item.subject}：${item.summary}`)
                          .join("\n") || "暂无"}
                      </p>
                    </div>
                  </>
                ) : (
                  <p className="hint-text">结构化记忆详情已折叠。</p>
                )}
              </div>
            ) : (
              <p>当前还没有章节生成结果，生成后会回写结构化记忆。</p>
            )}
          </section>
        </div>
      </div>

      <section className="panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Chapters</span>
            <h2>章节信息</h2>
          </div>
          <span className="hint-text">
            {props.taskData
              ? `当前任务状态：${translateLabel(props.taskData.task.status, statusLabels)}`
              : "从这里进入单章详情与人工确认。"}
          </span>
        </div>
        {props.taskData ? (
          <>
            <div className="section-title-row">
              <div>
                <span className="eyebrow">Current Task</span>
                <h3>当前任务章节</h3>
              </div>
              <span className="hint-text">
                {currentTaskChapters.length
                  ? `当前任务已生成 ${currentTaskChapters.length} 章`
                  : isTaskActive
                    ? "当前任务正在处理中，首个章节生成后会显示在这里。"
                    : "当前任务暂时没有章节数据。"}
              </span>
            </div>
            {currentTaskChapters.length ? (
              <div className="chapter-table">
                {currentTaskChapters.map((chapter: any) => (
                  <div key={chapter.id} className="chapter-row">
                    <div className="chapter-row-main">
                      <div>
                        <strong>{chapter.title}</strong>
                        <div>{translateLabel(chapter.status, statusLabels)}</div>
                      </div>
                    </div>
                    <div className="chapter-row-meta">回流次数：{chapter.rewrite_count}</div>
                    <div className="chapter-row-meta">{chapter.needs_manual_review ? labels.review.required : labels.review.notRequired}</div>
                    <button onClick={() => props.onOpenChapter(chapter.id)}>打开章节</button>
                  </div>
                ))}
              </div>
            ) : (
              <p>当前任务暂无可查看章节。</p>
            )}
          </>
        ) : null}
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Project History</span>
            <h3>全部章节</h3>
          </div>
          <span className="hint-text">保留整个项目的历史章节入口。</span>
        </div>
        {allProjectChapters.length ? (
          <div className="chapter-table">
            {allProjectChapters.map((chapter: any) => (
              <div key={chapter.id} className="chapter-row">
                <div className="chapter-row-main">
                  <div>
                    <strong>{chapter.title}</strong>
                    <div>{translateLabel(chapter.status, statusLabels)}</div>
                  </div>
                </div>
                <div className="chapter-row-meta">回流次数：{chapter.rewrite_count}</div>
                <div className="chapter-row-meta">{chapter.needs_manual_review ? labels.review.required : labels.review.notRequired}</div>
                <button onClick={() => props.onOpenChapter(chapter.id)}>打开章节</button>
              </div>
            ))}
          </div>
        ) : (
          <p>{props.projectData ? "当前项目还没有生成章节。" : "请选择一个项目。"}</p>
        )}
      </section>
    </>
  );
}

function TaskControlPanel(props: {
  projectData: any;
  quotaData: any;
  taskData: any;
  taskMode: Mode;
  chapterCount: number;
  loading: boolean;
  runningTask: boolean;
  hasActiveTask: boolean;
  onModeChange: (value: Mode) => void;
  onChapterCountChange: (value: number) => void;
  onRunTask: () => void;
  onClearActiveTask: () => void;
  onOpenChapter: (chapterId: string) => void;
}) {
  const actionLabel = props.runningTask ? "正在创作中..." : props.hasActiveTask ? "返回当前任务" : labels.actions.runTask;
  const actionHint = props.runningTask
    ? "正在创作中，系统会依次生成走向、正文并完成评分回流。"
    : props.hasActiveTask
      ? "当前项目已有未结束的续写任务，点击后会直接回到该任务。"
      : "";
  const configLocked = props.loading || props.hasActiveTask;
  const relayItems = buildTaskRelayItems(props.taskData);

  return (
    <section className="panel">
      <div className="section-title-row">
        <div>
          <span className="eyebrow">Task Control</span>
          <h2>{labels.sections.taskControl}</h2>
        </div>
      </div>
      <div className="inline">
        <label>
          {labels.fields.runMode}
          <select value={props.taskMode} onChange={(event) => props.onModeChange(event.target.value as Mode)} disabled={configLocked}>
            <option value="manual">{modeLabels.manual}</option>
            <option value="auto">{modeLabels.auto}</option>
          </select>
        </label>
        <label>
          {labels.fields.chapterCount}
          <input
            type="number"
            min={1}
            max={10}
            value={props.chapterCount}
            onChange={(event) => props.onChapterCountChange(Number(event.target.value))}
            disabled={configLocked}
          />
        </label>
        <button onClick={props.onRunTask} disabled={props.loading || !props.projectData?.project?.id}>
          {actionLabel}
        </button>
        {props.hasActiveTask ? (
          <button type="button" className="ghost-button" onClick={props.onClearActiveTask} disabled={props.loading}>
            清理当前任务
          </button>
        ) : null}
      </div>
      {actionHint ? <p className="hint-text">{actionHint}</p> : null}
      {props.hasActiveTask ? <p className="hint-text">当前任务未结束前，续写参数暂时锁定。</p> : null}
      {props.projectData ? (
        <div className="status-grid">
          <div><strong>{labels.info.project}</strong>{props.projectData.project.title}</div>
          <div><strong>{labels.info.quota}</strong>当日 {props.projectData.quota.daily_remaining} / 当月 {props.projectData.quota.monthly_remaining} / 赠送 {props.projectData.quota.bonus_remaining}</div>
          <div><strong>{labels.info.copyright}</strong>{props.projectData.copyright_notice}</div>
        </div>
      ) : null}
      {props.taskData ? (
        <div className="status-grid">
          <div><strong>{labels.info.taskStatus}</strong>{translateLabel(props.taskData.task.status, statusLabels)}</div>
          <div><strong>{labels.info.currentMode}</strong>{translateLabel(props.taskData.task.mode, modeLabels)}</div>
          <div><strong>{labels.info.currentChapter}</strong>第 {props.taskData.task.current_chapter_index} 章</div>
        </div>
      ) : null}
      {relayItems.length ? (
        <div className="task-relay-strip">
          {relayItems.map((item) => (
            <button
              key={`relay-${item.chapterIndex}`}
              type="button"
              className={`task-relay-pill task-relay-${item.tone}`}
              disabled={!item.chapterId}
              onClick={() => {
                if (item.chapterId) {
                  props.onOpenChapter(item.chapterId);
                }
              }}
            >
              <strong>第 {item.chapterIndex} 章</strong>
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      ) : null}
      {props.quotaData ? (
        <div className="status-grid">
          <div><strong>{labels.info.plans}</strong>{props.quotaData.default_plan.name}</div>
          <div>日免费章节 {props.quotaData.default_plan.daily_free_chapters}</div>
          <div>月免费章节 {props.quotaData.default_plan.monthly_free_chapters}</div>
          <div className="full hint-text">说明：日免费章节按自然日重置，月免费章节按自然月重置；消耗顺序为当日剩余，再扣当月剩余，最后扣赠送免费章节。</div>
        </div>
      ) : null}
    </section>
  );
}

function ChapterResultsPanel(props: {
  taskData: any;
  loading: boolean;
  activeActionKey: string;
  chapterTitleEdits: Record<string, string>;
  editingChapterTitles: Record<string, boolean>;
  chapterFeedbacks: Record<string, ChapterFeedback>;
  draftEdits: Record<string, string>;
  outlineEdits: Record<string, OutlineEdit>;
  chapterTransformInstructions: Record<string, string>;
  chapterTransformParagraphs: Record<string, string>;
  chapterTransformResults: Record<string, ChapterTransformResult>;
  onChapterTitleChange: (chapterId: string, value: string) => void;
  onChapterTitleEditingChange: (chapterId: string, value: boolean) => void;
  onSaveChapterTitle: (chapterId: string) => void;
  onOutlineEdit: (optionId: string, value: OutlineEdit) => void;
  onDraftEdit: (chapterId: string, value: string) => void;
  onChapterTransformInstructionChange: (chapterId: string, value: string) => void;
  onChapterTransformParagraphChange: (chapterId: string, value: string) => void;
  onConfirm: (chapterId: string) => void;
  onDeleteChapter: (chapterId: string) => void;
  onOutlineAction: (chapterId: string, action: "regenerate" | "select" | "save", option?: any) => void;
  onDraftAction: (chapter: any, action: "regenerate" | "save") => void;
  onChapterTransform: (chapter: any, action: "rewrite" | "expand" | "remove") => void;
}) {
  const [collapsedOutlineIds, setCollapsedOutlineIds] = useState<Record<string, boolean>>({});
  const [collapsedChapterSections, setCollapsedChapterSections] = useState<Record<string, { outlines: boolean; drafts: boolean; transforms: boolean }>>({});
  const [expandedFinalDrafts, setExpandedFinalDrafts] = useState<Record<string, boolean>>({});
  const [highlightedDraftId, setHighlightedDraftId] = useState("");

  function isEditable(chapter: any) {
    return !chapter.confirmed_by_user;
  }

  function canConfirmChapter(chapter: any) {
    return props.taskData?.task?.mode === "manual" && !chapter.confirmed_by_user;
  }

  function isActionRunning(actionKey: string) {
    return props.loading && props.activeActionKey === actionKey;
  }

  function hasConflictAlert(message: string) {
    return message.includes("设定冲突") || message.includes("冲突");
  }

  function renderConflictAlerts(draft: any) {
    const alerts = draft.conflict_alerts ?? [];
    if (!alerts.length) {
      return null;
    }
    return (
      <div className="conflict-detail-list">
        {alerts.map((alert: any, index: number) => (
          <div key={`${draft.id}-conflict-${index}`} className="conflict-detail-card">
            <div><strong>冲突对象：</strong>{alert.subject}</div>
            <div><strong>既有事实：</strong>{alert.existing_fact}</div>
            <div><strong>冲突线索：</strong>{alert.conflict_keyword}</div>
            <div><strong>提示：</strong>{alert.message}</div>
          </div>
        ))}
      </div>
    );
  }

  function isOutlineCollapsed(option: any) {
    if (option.selected) {
      return false;
    }
    return collapsedOutlineIds[option.id] ?? true;
  }

  function getChapterSectionState(chapterId: string) {
    return collapsedChapterSections[chapterId] ?? { outlines: true, drafts: true, transforms: true };
  }

  function openDraftSection(chapterId: string) {
    setCollapsedChapterSections((current) => ({
      ...current,
      [chapterId]: { ...getChapterSectionState(chapterId), drafts: false },
    }));
  }

  function jumpToDraftSection(chapterId: string) {
    openDraftSection(chapterId);
    const chapter = props.taskData?.chapters?.find((item: any) => item.id === chapterId);
    const conflictDraft = chapter?.drafts?.find((draft: any) => hasConflictAlert(String(draft.issue_summary ?? "")));
    if (conflictDraft?.id) {
      setHighlightedDraftId(conflictDraft.id);
      window.setTimeout(() => {
        setHighlightedDraftId((current) => (current === conflictDraft.id ? "" : current));
      }, 2200);
    }
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const targetId = conflictDraft?.id ? `draft-card-${conflictDraft.id}` : `chapter-drafts-${chapterId}`;
        document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function previewContent(content: string, expanded: boolean) {
    if (expanded || content.length <= 900) {
      return content;
    }
    return `${content.slice(0, 900).trimEnd()}...`;
  }

  function renderDiff(result: ChapterTransformResult, chapterId: string) {
    return (
      <div className="transform-result">
        <div className={hasConflictAlert(result.consistency_note) ? "conflict-alert" : ""}>
          <strong>一致性提示：</strong>{result.consistency_note}
        </div>
        <div className="diff-list">
          {result.diff.map((item, index) => (
            <div key={`${chapterId}-${index}`} className={item.type === "added" ? "diff-added" : item.type === "removed" ? "diff-removed" : ""}>
              {item.text}
            </div>
          ))}
        </div>
      </div>
    );
  }

  function renderSectionHeader(
    chapterId: string,
    section: "outlines" | "drafts" | "transforms",
    eyebrow: string,
    title: string,
    extraAction?: ReactNode,
  ) {
    const sectionState = getChapterSectionState(chapterId);
    const collapsed = sectionState[section];
    return (
      <div className="chapter-section-header">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h4>{title}</h4>
        </div>
        <div className="inline">
          {extraAction}
          <button
            type="button"
            className="ghost-button"
            onClick={() =>
              setCollapsedChapterSections((current) => ({
                ...current,
                [chapterId]: { ...getChapterSectionState(chapterId), [section]: !collapsed },
              }))
            }
          >
            {collapsed ? "展开" : "收起"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <section className="panel">
      <h2>{labels.sections.chapterResults}</h2>
      {props.taskData?.chapters?.length ? (
        props.taskData.chapters.map((chapter: any) => {
          const editable = isEditable(chapter);
          const selectedDraft = chapter.drafts.find((draft: any) => draft.selected) ?? chapter.drafts[chapter.drafts.length - 1];
          const chapterFeedback = props.chapterFeedbacks[chapter.id];
          const runtimeStatusMessage =
            chapter.status === "drafting"
              ? { tone: "working" as const, message: "正在生成正文，请稍候，生成完成后会自动刷新当前章节状态。" }
              : null;
          const feedbackToShow = chapterFeedback ?? runtimeStatusMessage;
          const sectionState = getChapterSectionState(chapter.id);
          return (
            <article key={chapter.id} className="chapter-card">
              <header>
                <div className="chapter-title-stack">
                  <h3>{chapter.title}</h3>
                  {editable ? (
                    props.editingChapterTitles[chapter.id] ? (
                      <div className="inline">
                        <label>
                          章节名称
                          <input
                            value={props.chapterTitleEdits[chapter.id] ?? chapter.title}
                            onChange={(event) => props.onChapterTitleChange(chapter.id, event.target.value)}
                          />
                        </label>
                        <button onClick={() => props.onSaveChapterTitle(chapter.id)} disabled={props.loading}>
                          {isActionRunning(`chapter-title-save:${chapter.id}`) ? "正在保存..." : "确认名称"}
                        </button>
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => {
                            props.onChapterTitleChange(chapter.id, chapter.title);
                            props.onChapterTitleEditingChange(chapter.id, false);
                          }}
                        >
                          取消
                        </button>
                      </div>
                    ) : (
                      <div className="inline">
                        <button
                          type="button"
                          className="ghost-button"
                          onClick={() => props.onChapterTitleEditingChange(chapter.id, true)}
                        >
                          编辑章节名称
                        </button>
                      </div>
                    )
                  ) : null}
                </div>
                <span>{translateLabel(chapter.status, statusLabels)}</span>
              </header>
              {feedbackToShow ? <div className={`action-feedback action-feedback-${feedbackToShow.tone}`}>{feedbackToShow.message}</div> : null}
              <div className="chapter-meta-strip">
                <div className="chapter-meta-pill">
                  <span>回流次数</span>
                  <strong>{chapter.rewrite_count}</strong>
                </div>
                <div className="chapter-meta-pill">
                  <span>人工复核</span>
                  <strong>{chapter.needs_manual_review ? labels.review.required : labels.review.notRequired}</strong>
                </div>
                <div className="chapter-meta-pill">
                  <span>版本数</span>
                  <strong>{chapter.drafts.length}</strong>
                </div>
                <div className="chapter-meta-pill">
                  <span>当前选中走向</span>
                  <strong>{chapter.outline_options.find((option: any) => option.selected)?.option_no ?? "-"}</strong>
                </div>
              </div>
              {chapter.drafts.some((draft: any) => hasConflictAlert(String(draft.issue_summary ?? ""))) ? (
                <button
                  type="button"
                  className="conflict-alert conflict-alert-button"
                  onClick={() => jumpToDraftSection(chapter.id)}
                >
                  当前章节存在设定冲突风险，请优先处理正文版本中的冲突提示。
                </button>
              ) : null}
              {editable ? <p className="hint-text">{labels.info.editableHint}，{labels.info.contentGoal}</p> : null}
              {selectedDraft ? (
                <div className="final-box final-box-prominent">
                  <div className="section-title-row">
                    <div>
                      <span className="eyebrow">Final Draft</span>
                      <h4>3. 最终正文</h4>
                    </div>
                    {editable ? (
                      <div className="chapter-action-groups">
                        <div className="inline">
                          <button onClick={() => props.onDraftAction(chapter, "save")} disabled={props.loading}>
                          {isActionRunning(`draft-save:${chapter.id}`) ? "正在保存..." : "保存改写"}
                          </button>
                          <button onClick={() => props.onDraftAction(chapter, "regenerate")} disabled={props.loading}>
                            {isActionRunning(`draft-regenerate:${chapter.id}`) ? "正在 AI 重写..." : "AI 重写"}
                          </button>
                        </div>
                        <div className="inline">
                          <button className="danger-button" onClick={() => props.onDeleteChapter(chapter.id)} disabled={props.loading}>
                            {isActionRunning(`chapter-delete:${chapter.id}`) ? "正在删除..." : "删除整章"}
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                  {editable ? (
                    <textarea className="chapter-editor" rows={18} value={props.draftEdits[chapter.id] ?? selectedDraft.content} onChange={(event) => props.onDraftEdit(chapter.id, event.target.value)} />
                  ) : (
                    <>
                      <pre className="content-block">{previewContent(selectedDraft.content, expandedFinalDrafts[chapter.id] ?? false)}</pre>
                      {selectedDraft.content.length > 900 ? (
                        <div className="inline">
                          <button
                            type="button"
                            className="ghost-button"
                            onClick={() =>
                              setExpandedFinalDrafts((current) => ({
                                ...current,
                                [chapter.id]: !(current[chapter.id] ?? false),
                              }))
                            }
                          >
                            {(expandedFinalDrafts[chapter.id] ?? false) ? "收起全文" : "展开全部"}
                          </button>
                        </div>
                      ) : null}
                    </>
                  )}
                  {editable ? <p className="hint-text">`保存改写` 会保存当前正文，`AI 重写` 会重新生成正文。</p> : null}
                  {canConfirmChapter(chapter) ? (
                    <div className="chapter-primary-action">
                      <button onClick={() => props.onConfirm(chapter.id)} disabled={props.loading}>
                        {isActionRunning(`chapter-confirm:${chapter.id}`) ? "正在确认..." : labels.actions.confirmChapter}
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="chapter-detail-layout">
                <section className="chapter-stage chapter-stage-panel">
                  {renderSectionHeader(
                    chapter.id,
                    "outlines",
                    "Outline",
                    "1. 剧情走向",
                    editable ? (
                      <button onClick={() => props.onOutlineAction(chapter.id, "regenerate")} disabled={props.loading}>
                        {isActionRunning(`outline-regenerate:${chapter.id}`) ? "正在重生成走向..." : labels.actions.regenerateOutlines}
                      </button>
                    ) : undefined,
                  )}
                  {sectionState.outlines ? (
                    <p className="hint-text">剧情走向已折叠。</p>
                  ) : (
                    <>
                      {props.taskData?.memory?.active_phase && Object.keys(props.taskData.memory.active_phase).length > 0 ? (
                        <div className="outline-phase-brief">
                          <div className="phase-highlight-meta">
                            <span className="phase-chip">Phase {props.taskData.memory.active_phase.phase_index ?? "-"}</span>
                            <span className="phase-status">{props.taskData.memory.active_phase.status ?? "active"}</span>
                          </div>
                          <strong>{props.taskData.memory.active_phase.label ?? "当前阶段"}</strong>
                          <p>{props.taskData.memory.active_phase.phase_goal ?? "暂无阶段目标"}</p>
                        </div>
                      ) : null}
                      {chapter.outline_options.map((option: any) => {
                      const phaseScore = scoreOutlineAgainstPhase(option, props.taskData?.memory?.active_phase ?? {});
                      const edit = props.outlineEdits[option.id] ?? {
                        content: option.content,
                        core_conflict: option.core_conflict,
                        key_event: option.key_event,
                        ending_hook: option.ending_hook,
                      };
                      const collapsed = isOutlineCollapsed(option);
                      return (
                        <div key={option.id} className={option.selected ? "selected card" : "card"}>
                          <div className="section-title-row">
                            <div>
                              <strong>方案 {option.option_no}</strong> {option.selected ? labels.selection.selected : ""}
                            </div>
                            {!option.selected ? (
                              <button
                                type="button"
                                className="ghost-button"
                                onClick={() =>
                                  setCollapsedOutlineIds((current) => ({
                                    ...current,
                                    [option.id]: !collapsed,
                                  }))
                                }
                              >
                                {collapsed ? "展开" : "收起"}
                              </button>
                            ) : null}
                          </div>
                          {collapsed ? (
                            <p className="hint-text">该方案已折叠。</p>
                          ) : (
                            <>
                              <div className={`phase-fit-badge phase-fit-${phaseScore.tone}`}>
                                <strong>{phaseScore.label}</strong>
                                {phaseScore.hits.length ? <span>命中：{phaseScore.hits.join(" / ")}</span> : <span>当前方案与阶段目标的直接呼应较少。</span>}
                              </div>
                              {editable ? (
                                <div className="editor-grid">
                                  <label>走向内容<textarea rows={5} value={edit.content} onChange={(event) => props.onOutlineEdit(option.id, { ...edit, content: event.target.value })} /></label>
                                  <label>核心冲突<textarea rows={3} value={edit.core_conflict} onChange={(event) => props.onOutlineEdit(option.id, { ...edit, core_conflict: event.target.value })} /></label>
                                  <label>关键事件<textarea rows={3} value={edit.key_event} onChange={(event) => props.onOutlineEdit(option.id, { ...edit, key_event: event.target.value })} /></label>
                                  <label>结尾钩子<textarea rows={3} value={edit.ending_hook} onChange={(event) => props.onOutlineEdit(option.id, { ...edit, ending_hook: event.target.value })} /></label>
                                </div>
                              ) : (
                                <>
                                  <div>{option.content}</div>
                                  <div>核心冲突：{option.core_conflict}</div>
                                  <div>关键事件：{option.key_event}</div>
                                  <div>结尾钩子：{option.ending_hook}</div>
                                </>
                              )}
                              <div>
                                评分：情节推进 {option.score_plot}，连贯性 {option.score_consistency}，吸引力 {option.score_hook}，阶段贴合 {option.score_phase_fit ?? "-"}，总分 {option.final_score}
                              </div>
                              <div>{option.editor_comment}</div>
                              {editable ? (
                                <div className="inline">
                                  <button onClick={() => props.onOutlineAction(chapter.id, "select", option)} disabled={props.loading}>
                                    {isActionRunning(`outline-select:${chapter.id}:${option.id}`) ? "正在选用..." : labels.actions.selectOutline}
                                  </button>
                                  <button onClick={() => props.onOutlineAction(chapter.id, "save", option)} disabled={props.loading}>
                                    {isActionRunning(`outline-save:${chapter.id}:${option.id}`) ? "正在保存..." : labels.actions.saveOutline}
                                  </button>
                                </div>
                              ) : null}
                            </>
                          )}
                        </div>
                      );
                    })}
                    </>
                  )}
                </section>
                <section id={`chapter-drafts-${chapter.id}`} className="chapter-stage chapter-stage-panel">
                  {renderSectionHeader(chapter.id, "drafts", "Draft Versions", "2. 正文版本")}
                  {sectionState.drafts ? (
                    <p className="hint-text">正文版本已折叠。</p>
                  ) : (
                    chapter.drafts.map((draft: any) => {
                      const hasDraftConflict = hasConflictAlert(String(draft.issue_summary ?? ""));
                      return (
                        <div
                          id={`draft-card-${draft.id}`}
                          key={draft.id}
                          className={[
                            draft.selected ? "selected card" : "card",
                            highlightedDraftId === draft.id ? "conflict-focus-card" : "",
                          ].filter(Boolean).join(" ")}
                        >
                          <div><strong>修订稿 {draft.revision_no}</strong> {draft.selected ? labels.selection.final : ""}</div>
                          <div>读者评分：{draft.final_score}</div>
                          <div>问题说明：{draft.issue_summary}</div>
                          {hasDraftConflict ? (
                            <div className="conflict-alert">检测到设定冲突，请在人工确认前先修复。</div>
                          ) : null}
                          {renderConflictAlerts(draft)}
                        </div>
                      );
                    })
                  )}
                </section>
                <section className="chapter-stage chapter-stage-panel">
                  {renderSectionHeader(chapter.id, "transforms", "AI Actions", "4. 章节级 AI 处理")}
                  {sectionState.transforms ? (
                    <p className="hint-text">章节级 AI 处理已折叠。</p>
                  ) : (
                    <>
                      <label>
                        本章处理要求
                        <textarea
                          rows={3}
                          value={props.chapterTransformInstructions[chapter.id] ?? ""}
                          onChange={(event) => props.onChapterTransformInstructionChange(chapter.id, event.target.value)}
                          placeholder="例如：重写整章，强化人物冲突；或：拓写整章，补足环境与情绪细节。"
                        />
                      </label>
                      <label>
                        目标段落（可选）
                        <textarea
                          rows={4}
                          value={props.chapterTransformParagraphs[chapter.id] ?? ""}
                          onChange={(event) => props.onChapterTransformParagraphChange(chapter.id, event.target.value)}
                          placeholder="填写需要处理的原始段落；留空则按整章处理。"
                        />
                      </label>
                      <div className="inline">
                        <button onClick={() => props.onChapterTransform(chapter, "rewrite")} disabled={props.loading}>
                          {isActionRunning(`chapter-transform:rewrite:${chapter.id}`) ? "正在整章重写..." : "整章重写"}
                        </button>
                        <button onClick={() => props.onChapterTransform(chapter, "expand")} disabled={props.loading}>
                          {isActionRunning(`chapter-transform:expand:${chapter.id}`) ? "正在整章拓写..." : "整章拓写"}
                        </button>
                        <button onClick={() => props.onChapterTransform(chapter, "remove")} disabled={props.loading}>
                          {isActionRunning(`chapter-transform:remove:${chapter.id}`) ? "正在去除段落..." : "去除段落"}
                        </button>
                      </div>
                      {props.chapterTransformResults[chapter.id] ? (
                        renderDiff(props.chapterTransformResults[chapter.id], chapter.id)
                      ) : (
                        <p className="hint-text">处理结果会显示在这里，并同步回填正文。</p>
                      )}
                    </>
                  )}
                </section>
              </div>
            </article>
          );
        })
      ) : (
        <p>{labels.states.noChapterResults}</p>
      )}
    </section>
  );
}

function AdminMembershipPage(props: {
  memberships: any;
  users: Array<{ id: string; username: string; role: "creator" | "admin" }>;
  quotaAdjustForm: { targetUserId: string; dailyDelta: number; monthlyDelta: number; bonusDelta: number };
  planForm: PlanForm;
  editingPlanId: string;
  planModalOpen: boolean;
  loading: boolean;
  onQuotaChange: (value: { targetUserId: string; dailyDelta: number; monthlyDelta: number; bonusDelta: number }) => void;
  onMembershipTargetChange: (targetUserId: string) => void;
  onLoadMembershipTarget: () => void;
  onPlanFormChange: (value: PlanForm) => void;
  onAdjustQuota: () => void;
  onPlanSubmit: (event: FormEvent) => void;
  onEditPlan: (plan: any) => void;
  onCreatePlan: () => void;
  onClosePlanModal: () => void;
  onActivatePlan: (planId: string) => void;
}) {
  const plans = props.memberships?.plans ?? [];
  const targetUser = props.users.find((user) => user.id === props.quotaAdjustForm.targetUserId);
  const defaultPlan = props.memberships?.default_plan;
  return (
    <div className="admin-workbench">
      <section className="panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Quota</span>
            <h2>额度概览</h2>
          </div>
          <span className="hint-text">先看当前生效套餐与剩余额度，再决定是否调额。</span>
        </div>
        <div className="template-stat-grid">
          <div className="summary-box">
            <span className="summary-label">{labels.info.activePlan}</span>
            <strong>{defaultPlan?.name ?? "-"}</strong>
          </div>
          <div className="summary-box">
            <span className="summary-label">日免费章节</span>
            <strong>{defaultPlan?.daily_free_chapters ?? 0}</strong>
          </div>
          <div className="summary-box">
            <span className="summary-label">月免费章节</span>
            <strong>{defaultPlan?.monthly_free_chapters ?? 0}</strong>
          </div>
          <div className="summary-box">
            <span className="summary-label">赠送免费章节</span>
            <strong>{props.memberships?.quota?.bonus_remaining ?? 0}</strong>
          </div>
          <div className="summary-box">
            <span className="summary-label">当日剩余</span>
            <strong>{props.memberships?.quota?.daily_remaining ?? 0}</strong>
          </div>
          <div className="summary-box">
            <span className="summary-label">当月剩余</span>
            <strong>{props.memberships?.quota?.monthly_remaining ?? 0}</strong>
          </div>
          <div className="summary-box">
            <span className="summary-label">套餐总数</span>
            <strong>{plans.length}</strong>
          </div>
        </div>
        <div className="inline">
          <label>
            目标用户
            <input
              value={props.quotaAdjustForm.targetUserId}
              onChange={(event) => props.onMembershipTargetChange(event.target.value)}
              placeholder="为空则查看全局默认额度"
            />
          </label>
          <button onClick={props.onLoadMembershipTarget} disabled={props.loading}>加载目标额度</button>
          <label>
            {labels.fields.dailyDelta}
            <input type="number" value={props.quotaAdjustForm.dailyDelta} onChange={(event) => props.onQuotaChange({ ...props.quotaAdjustForm, dailyDelta: Number(event.target.value) })} />
          </label>
          <label>
            {labels.fields.monthlyDelta}
            <input type="number" value={props.quotaAdjustForm.monthlyDelta} onChange={(event) => props.onQuotaChange({ ...props.quotaAdjustForm, monthlyDelta: Number(event.target.value) })} />
          </label>
          <label>
            {labels.fields.bonusDelta}
            <input type="number" value={props.quotaAdjustForm.bonusDelta} onChange={(event) => props.onQuotaChange({ ...props.quotaAdjustForm, bonusDelta: Number(event.target.value) })} />
          </label>
          <button onClick={props.onAdjustQuota} disabled={props.loading}>{labels.actions.adjustQuota}</button>
        </div>
        <div className="hint-text">
          当前目标：{targetUser ? `${targetUser.username} (${targetUser.id})` : props.quotaAdjustForm.targetUserId || "全局默认额度"}
        </div>
        <div className="hint-text">
          规则说明：日免费章节按自然日重置，月免费章节按自然月重置；实际扣减顺序为当日剩余，再扣当月剩余，最后扣赠送免费章节。
        </div>
      </section>

      <div className="admin-side-stack">
        <section className="panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Plan List</span>
              <h2>套餐列表</h2>
            </div>
            <span className="hint-text">区分当前生效套餐与可切换套餐。</span>
          </div>
          <div className="inline">
            <button onClick={props.onCreatePlan} disabled={props.loading}>{labels.actions.createPlan}</button>
          </div>
          <div className="log-list">
            {plans.map((plan: any) => (
              <div key={plan.id} className="card">
                <div className="section-title-row">
                  <div>
                    <strong>{plan.name}</strong>
                    <div>{plan.id}</div>
                  </div>
                  {props.memberships?.default_plan_id === plan.id ? <span className="badge">当前默认</span> : null}
                </div>
                <div>日免费章节 {plan.daily_free_chapters} / 月免费章节 {plan.monthly_free_chapters}</div>
                <div>{plan.description || "暂无说明"}</div>
                <div className="inline">
                  <button onClick={() => props.onEditPlan(plan)}>{labels.actions.editPlan}</button>
                  {props.memberships?.default_plan_id !== plan.id ? (
                    <button onClick={() => props.onActivatePlan(plan.id)} disabled={props.loading}>{labels.actions.activatePlan}</button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
      {props.planModalOpen ? (
        <div className="modal-backdrop" onClick={props.onClosePlanModal}>
          <div className="modal-panel" onClick={(event) => event.stopPropagation()}>
            <div className="section-title-row">
              <div>
                <span className="eyebrow">Plans</span>
                <h2>{props.editingPlanId ? "编辑套餐" : "新建套餐"}</h2>
              </div>
              <button type="button" className="ghost-button" onClick={props.onClosePlanModal}>关闭</button>
            </div>
            <form onSubmit={props.onPlanSubmit} className="form-grid">
              <label>
                {labels.fields.planName}
                <input value={props.planForm.name} onChange={(event) => props.onPlanFormChange({ ...props.planForm, name: event.target.value })} />
              </label>
              <label>
                {labels.fields.planDailyQuota}
                <input type="number" min={0} value={props.planForm.daily_free_chapters} onChange={(event) => props.onPlanFormChange({ ...props.planForm, daily_free_chapters: Number(event.target.value) })} />
              </label>
              <label>
                {labels.fields.planMonthlyQuota}
                <input type="number" min={0} value={props.planForm.monthly_free_chapters} onChange={(event) => props.onPlanFormChange({ ...props.planForm, monthly_free_chapters: Number(event.target.value) })} />
              </label>
              <label className="full">
                {labels.fields.planDescription}
                <textarea rows={3} value={props.planForm.description} onChange={(event) => props.onPlanFormChange({ ...props.planForm, description: event.target.value })} />
              </label>
              <button type="submit" disabled={props.loading}>{labels.actions.savePlan}</button>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function AdminUsersPage(props: {
  users: Array<{ id: string; username: string; role: "creator" | "admin" }>;
  adminUserForm: { username: string };
  loading: boolean;
  onAdminUserFormChange: (value: { username: string }) => void;
  onCreateUser: () => void;
  onResetUserPassword: (userId: string) => void;
  onSetMembershipTarget: (userId: string) => void;
}) {
  return (
    <div className="admin-workbench">
      <section className="panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Accounts</span>
            <h2>账号管理</h2>
          </div>
          <span className="hint-text">支持管理员创建客户，并将客户密码重置为 `11111111`。</span>
        </div>
        <div className="inline">
          <label>
            新客户用户名
            <input
              value={props.adminUserForm.username}
              onChange={(event) => props.onAdminUserFormChange({ username: event.target.value })}
              placeholder="输入新客户用户名"
            />
          </label>
          <button onClick={props.onCreateUser} disabled={props.loading}>创建客户</button>
        </div>
        <div className="hint-text">新创建客户默认密码：`11111111`</div>
      </section>

      <section className="panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Users</span>
            <h2>账号列表</h2>
          </div>
          <span className="hint-text">可直接跳转到额度管理并设置目标账号。</span>
        </div>
        <div className="log-list">
          {props.users.map((user) => (
            <div key={user.id} className="card">
              <div className="section-title-row">
                <div>
                  <strong>{user.username}</strong>
                  <div>{user.id}</div>
                </div>
                <span className="badge">{user.role}</span>
              </div>
              <div className="inline">
                <button onClick={() => props.onSetMembershipTarget(user.id)} disabled={props.loading}>
                  设为额度目标
                </button>
                {user.role === "creator" ? (
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => props.onResetUserPassword(user.id)}
                    disabled={props.loading}
                  >
                    重置密码为 11111111
                  </button>
                ) : null}
              </div>
            </div>
          ))}
          {!props.users.length ? <p>当前还没有可用账号。</p> : null}
        </div>
      </section>
    </div>
  );
}

function AdminOrdersPage(props: {
  memberships: any;
  orders: any[];
  orderForm: OrderForm;
  editingOrderId: string;
  loading: boolean;
  onOrderFormChange: (value: OrderForm) => void;
  onOrderSubmit: (event: FormEvent) => void;
  onEditOrder: (order: any) => void;
}) {
  const paidOrders = props.orders.filter((order) => String(order.status).includes("已支付"));
  const pendingOrders = props.orders.filter((order) => !String(order.status).includes("已支付"));
  return (
    <div className="admin-workbench">
      <section className="panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Orders</span>
            <h2>订单录入与编辑</h2>
          </div>
          <span className="hint-text">处理支付状态、套餐绑定与运营备注。</span>
        </div>
        <div className="template-stat-grid">
          <div className="summary-box">
            <span className="summary-label">订单总数</span>
            <strong>{props.orders.length}</strong>
          </div>
          <div className="summary-box">
            <span className="summary-label">待处理</span>
            <strong>{pendingOrders.length}</strong>
          </div>
          <div className="summary-box">
            <span className="summary-label">已支付</span>
            <strong>{paidOrders.length}</strong>
          </div>
        </div>
        <form onSubmit={props.onOrderSubmit} className="form-grid">
          <label>
            {labels.fields.planName}
            <select value={props.orderForm.plan_id} onChange={(event) => props.onOrderFormChange({ ...props.orderForm, plan_id: event.target.value })}>
              {(props.memberships?.plans ?? []).map((plan: any) => (
                <option key={plan.id} value={plan.id}>
                  {plan.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {labels.fields.orderAmount}
            <input type="number" min={0} step="0.1" value={props.orderForm.amount} onChange={(event) => props.onOrderFormChange({ ...props.orderForm, amount: Number(event.target.value) })} />
          </label>
          <label>
            {labels.fields.orderStatus}
            <input value={props.orderForm.status} onChange={(event) => props.onOrderFormChange({ ...props.orderForm, status: event.target.value })} />
          </label>
          <label className="full">
            {labels.fields.orderNote}
            <textarea rows={3} value={props.orderForm.note} onChange={(event) => props.onOrderFormChange({ ...props.orderForm, note: event.target.value })} />
          </label>
          <button type="submit" disabled={props.loading}>{props.editingOrderId ? labels.actions.saveOrder : labels.actions.createOrder}</button>
        </form>
      </section>

      <div className="admin-side-stack">
        <section className="panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Pending</span>
              <h2>待处理订单</h2>
            </div>
            <span className="hint-text">优先更新支付状态与运营备注。</span>
          </div>
          <div className="log-list">
            {pendingOrders.map((order) => (
              <div key={order.id} className="card">
                <div className="section-title-row">
                  <strong>{order.id}</strong>
                  <span>{order.status}</span>
                </div>
                <div>套餐 {order.plan_id} / 金额 {order.amount}</div>
                <div>{order.note || "暂无备注"}</div>
                <button onClick={() => props.onEditOrder(order)}>{labels.actions.saveOrder}</button>
              </div>
            ))}
            {!pendingOrders.length ? <p>暂无待处理订单。</p> : null}
          </div>
        </section>

        <section className="panel">
          <div className="section-title-row">
            <div>
              <span className="eyebrow">Paid</span>
              <h2>已支付订单</h2>
            </div>
            <span className="hint-text">保留作为已完成履约记录。</span>
          </div>
          <div className="log-list">
            {paidOrders.map((order) => (
              <div key={order.id} className="card">
                <div className="section-title-row">
                  <strong>{order.id}</strong>
                  <span className="badge">已支付</span>
                </div>
                <div>套餐 {order.plan_id} / 金额 {order.amount}</div>
                <div>{order.note || "暂无备注"}</div>
              </div>
            ))}
            {!paidOrders.length ? <p>暂无已支付订单。</p> : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function AdminSafetyPage(props: {
  safetyForm: { blockedTerms: string; copyrightNotice: string };
  loading: boolean;
  onSafetyFormChange: (value: { blockedTerms: string; copyrightNotice: string }) => void;
  onSave: () => void;
}) {
  return (
    <section className="panel">
      <div className="section-title-row">
        <div>
          <span className="eyebrow">Safety</span>
          <h2>{labels.info.safety}</h2>
        </div>
      </div>
      <div className="editor-grid">
        <label>
          {labels.fields.blockedTerms}
          <textarea rows={6} value={props.safetyForm.blockedTerms} onChange={(event) => props.onSafetyFormChange({ ...props.safetyForm, blockedTerms: event.target.value })} />
        </label>
        <label>
          {labels.fields.copyrightNotice}
          <textarea rows={4} value={props.safetyForm.copyrightNotice} onChange={(event) => props.onSafetyFormChange({ ...props.safetyForm, copyrightNotice: event.target.value })} />
        </label>
        <button onClick={props.onSave} disabled={props.loading}>{labels.actions.saveSafety}</button>
      </div>
    </section>
  );
}

function AdminGenrePage(props: {
  genres: Array<{ value: string; label: string; required_any: string[]; forbidden_any: string[] }>;
  form: GenreAdminForm;
  loading: boolean;
  onFormChange: (value: GenreAdminForm) => void;
  onSave: () => void;
  onEdit: (genre: { value: string; label: string; required_any: string[]; forbidden_any: string[] }) => void;
}) {
  return (
    <div className="admin-workbench">
      <section className="panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Genres</span>
            <h2>题材规则</h2>
          </div>
          <span className="hint-text">题材正负信号改这里，生成与审查链路会直接读取。</span>
        </div>
        <div className="editor-grid">
          <label>
            题材标识
            <input value={props.form.value} onChange={(event) => props.onFormChange({ ...props.form, value: event.target.value })} />
          </label>
          <label>
            展示名称
            <input value={props.form.label} onChange={(event) => props.onFormChange({ ...props.form, label: event.target.value })} />
          </label>
          <label>
            required_any
            <textarea rows={6} value={props.form.required_any} onChange={(event) => props.onFormChange({ ...props.form, required_any: event.target.value })} />
          </label>
          <label>
            forbidden_any
            <textarea rows={6} value={props.form.forbidden_any} onChange={(event) => props.onFormChange({ ...props.form, forbidden_any: event.target.value })} />
          </label>
          <button onClick={props.onSave} disabled={props.loading}>保存题材规则</button>
        </div>
      </section>

      <section className="panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Rule Set</span>
            <h2>已配置题材</h2>
          </div>
        </div>
        <div className="log-list">
          {props.genres.map((genre) => (
            <div key={genre.value} className="card">
              <div className="section-title-row">
                <strong>{genre.label} / {genre.value}</strong>
                <button type="button" onClick={() => props.onEdit(genre)}>编辑</button>
              </div>
              <div><strong>required_any：</strong>{genre.required_any.join(" / ") || "暂无"}</div>
              <div><strong>forbidden_any：</strong>{genre.forbidden_any.join(" / ") || "暂无"}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function AdminLogsPage(props: { logs: any[] }) {
  const actionCounts = props.logs.reduce<Record<string, number>>((acc, log) => {
    acc[log.action] = (acc[log.action] ?? 0) + 1;
    return acc;
  }, {});
  const actionEntries = Object.entries(actionCounts).sort((left, right) => right[1] - left[1]);
  return (
    <div className="admin-workbench">
      <section className="panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Logs</span>
            <h2>{labels.info.logs}</h2>
          </div>
          <span className="hint-text">先看事件分布，再下钻到单条日志。</span>
        </div>
        <div className="template-stat-grid">
          <div className="summary-box">
            <span className="summary-label">日志总数</span>
            <strong>{props.logs.length}</strong>
          </div>
          {actionEntries.slice(0, 3).map(([action, count]) => (
            <div key={action} className="summary-box">
              <span className="summary-label">{action}</span>
              <strong>{count}</strong>
            </div>
          ))}
        </div>
        <div className="log-list">
          {actionEntries.map(([action, count]) => (
            <div key={action} className="card">
              <div className="section-title-row">
                <strong>{action}</strong>
                <span>{count} 次</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="section-title-row">
          <div>
            <span className="eyebrow">Log Detail</span>
            <h2>日志明细</h2>
          </div>
          <span className="hint-text">按时间倒序检查任务链路与后台动作。</span>
        </div>
        <div className="log-list">
          {props.logs.map((log) => (
            <div key={log.id} className="card">
              <div className="log-meta">
                <strong>{labels.info.logAction}：{log.action}</strong>
                <span>{labels.info.logTime}：{log.created_at}</span>
              </div>
              <pre className="content-block">{JSON.stringify(log.details, null, 2)}</pre>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export default function App() {
  const initialWorkspace = readWorkspaceState();
  const [route, setRoute] = useState<Route>(readRoute());
  const [session, setSession] = useState<Session | null>(() => readSession());
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authConfirmPassword, setAuthConfirmPassword] = useState("");
  const [passwordForm, setPasswordForm] = useState<PasswordForm>(initialPasswordForm);
  const [form, setForm] = useState<ProjectForm>(initialForm);
  const [projects, setProjects] = useState<any[]>([]);
  const [genres, setGenres] = useState<Array<{ value: string; label: string }>>([]);
  const [selectedProjectId, setSelectedProjectId] = useState(initialWorkspace.selectedProjectId);
  const [selectedTaskId, setSelectedTaskId] = useState(initialWorkspace.selectedTaskId);
  const [selectedChapterId, setSelectedChapterId] = useState(initialWorkspace.selectedChapterId);
  const [projectData, setProjectData] = useState<any>(null);
  const [taskData, setTaskData] = useState<any>(null);
  const [chapterDetailData, setChapterDetailData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [runningTask, setRunningTask] = useState(false);
  const [error, setError] = useState("");
  const [taskMode, setTaskMode] = useState<Mode>("manual");
  const [chapterCount, setChapterCount] = useState(3);
  const [activeActionKey, setActiveActionKey] = useState("");
  const [busyMessage, setBusyMessage] = useState("");
  const [restoredFoundationBusyMessage, setRestoredFoundationBusyMessage] = useState(() => readFoundationBusyMessage());
  const [busyStartedAt, setBusyStartedAt] = useState<number | null>(null);
  const [busyElapsedSeconds, setBusyElapsedSeconds] = useState(0);
  const [busyProgressStage, setBusyProgressStage] = useState("");
  const [busyProgressMessage, setBusyProgressMessage] = useState("");
  const [foundationTaskId, setFoundationTaskId] = useState(() => readFoundationTaskId());
  const [outlineEdits, setOutlineEdits] = useState<Record<string, OutlineEdit>>({});
  const [chapterTitleEdits, setChapterTitleEdits] = useState<Record<string, string>>({});
  const [editingChapterTitles, setEditingChapterTitles] = useState<Record<string, boolean>>({});
  const [chapterFeedbacks, setChapterFeedbacks] = useState<Record<string, ChapterFeedback>>({});
  const [nextChapterReadyNotice, setNextChapterReadyNotice] = useState<NextChapterReadyNotice | null>(null);
  const [draftEdits, setDraftEdits] = useState<Record<string, string>>({});
  const [chapterTransformInstructions, setChapterTransformInstructions] = useState<Record<string, string>>({});
  const [chapterTransformParagraphs, setChapterTransformParagraphs] = useState<Record<string, string>>({});
  const [chapterTransformResults, setChapterTransformResults] = useState<Record<string, ChapterTransformResult>>({});
  const [quotaData, setQuotaData] = useState<any>(null);
  const [adminData, setAdminData] = useState<any>({
    memberships: null,
    users: [],
    orders: [],
    safety: null,
    logs: [],
    genres: [],
  });
  const [quotaAdjustForm, setQuotaAdjustForm] = useState({ targetUserId: "", dailyDelta: 0, monthlyDelta: 0, bonusDelta: 0 });
  const [safetyForm, setSafetyForm] = useState({ blockedTerms: "", copyrightNotice: "" });
  const [planForm, setPlanForm] = useState<PlanForm>(initialPlanForm);
  const [editingPlanId, setEditingPlanId] = useState("");
  const [planModalOpen, setPlanModalOpen] = useState(false);
  const [orderForm, setOrderForm] = useState<OrderForm>(initialOrderForm);
  const [editingOrderId, setEditingOrderId] = useState("");
  const [adminUserForm, setAdminUserForm] = useState<AdminUserForm>(initialAdminUserForm);
  const [genreAdminForm, setGenreAdminForm] = useState<GenreAdminForm>(initialGenreAdminForm);

  const overlayMessage = loading && busyMessage ? busyMessage : !loading ? restoredFoundationBusyMessage : "";
  const overlayDetail =
    busyProgressMessage ||
    (overlayMessage === "正在生成项目基础设定..."
      ? "系统正在根据你当前填写的信息优化总纲摘要、角色卡、世界规则和事件摘要，完成后会自动回填表单。"
      : overlayMessage === "正在创建并执行续写任务..."
        ? "系统正在依次生成章节走向、正文与评分结果。生成完成后会自动刷新当前项目和章节状态。"
        : overlayMessage === "正在重生成正文..."
          ? "系统正在调用模型重写当前章节正文，完成后会自动更新当前章节。"
          : overlayMessage || "系统正在处理中。");
  const overlayStageDetail = (() => {
    if (busyProgressStage === "input_analysis") {
      return "当前阶段：整理客户输入";
    }
    if (busyProgressStage === "foundation_generation") {
      return "当前阶段：生成基础设定建议";
    }
    if (busyProgressStage === "task_starting") {
      return "当前阶段：启动生成任务";
    }
    if (busyProgressStage === "chapter_preparing") {
      return "当前阶段：准备章节上下文";
    }
    if (busyProgressStage === "outline_generation") {
      return "当前阶段：生成章节走向";
    }
    if (busyProgressStage === "draft_generation") {
      return "当前阶段：生成章节正文";
    }
    if (busyProgressStage === "draft_review") {
      return "当前阶段：评分与一致性审查";
    }
    if (busyProgressStage === "memory_sync") {
      return "当前阶段：回写章节记忆";
    }
    if (busyProgressStage === "waiting_user_confirm") {
      return "当前阶段：等待人工确认";
    }
    if (busyProgressStage === "chapter_completed") {
      return "当前阶段：单章已完成";
    }
    if (busyProgressStage === "completed") {
      return "当前阶段：处理完成";
    }
    if (busyProgressStage === "failed") {
      return "当前阶段：处理失败";
    }
    if (!overlayMessage) {
      return "";
    }
    if (overlayMessage === "正在创建并执行续写任务...") {
      return "当前阶段：创建任务并启动章节生成";
    }
    if (activeActionKey.startsWith("outline-regenerate:")) {
      return "当前阶段：重新生成章节走向";
    }
    if (activeActionKey.startsWith("outline-select:")) {
      return "当前阶段：保存选中的章节走向";
    }
    if (activeActionKey.startsWith("draft-regenerate:")) {
      return "当前阶段：重新生成章节正文";
    }
    if (activeActionKey.startsWith("draft-save:")) {
      return "当前阶段：保存人工修改后的正文";
    }
    if (activeActionKey.startsWith("chapter-transform:rewrite:")) {
      return "当前阶段：整章重写";
    }
    if (activeActionKey.startsWith("chapter-transform:expand:")) {
      return "当前阶段：整章拓写";
    }
    if (activeActionKey.startsWith("chapter-transform:remove:")) {
      return "当前阶段：去除指定段落";
    }
    if (activeActionKey.startsWith("chapter-confirm:")) {
      if (busyProgressStage === "outline_generation") {
        return "当前阶段：已确认本章，正在生成下一章走向";
      }
      if (busyProgressStage === "draft_generation") {
        return "当前阶段：已确认本章，正在生成下一章正文";
      }
      if (busyProgressStage === "draft_review") {
        return "当前阶段：已确认本章，正在评审下一章正文";
      }
      if (busyProgressStage === "memory_sync") {
        return "当前阶段：已确认本章，正在回写下一章记忆";
      }
      if (busyProgressStage === "chapter_preparing") {
        return "当前阶段：已确认本章，正在准备下一章上下文";
      }
      return "当前阶段：确认章节并推进任务状态";
    }
    if (activeActionKey.startsWith("chapter-delete:")) {
      return "当前阶段：删除章节并刷新项目";
    }
    if (activeActionKey.startsWith("chapter-title-save:")) {
      return "当前阶段：保存章节名称";
    }
    if (overlayMessage === "正在生成项目基础设定...") {
      return "当前阶段：整理客户输入并生成优化建议";
    }
    return "当前阶段：系统处理中";
  })();

  function findActiveTask(project: any) {
    return project?.tasks?.find((task: any) => ["queued", "running", "waiting_user_confirm"].includes(task.status)) ?? null;
  }

  function findTaskForChapter(project: any, chapterId: string) {
    const tasks = Array.isArray(project?.tasks) ? project.tasks : [];
    const chapters = Array.isArray(project?.chapters) ? project.chapters : [];
    const chapter = chapters.find((item: any) => item?.id === chapterId);
    const chapterIndex = Number(chapter?.chapter_index ?? 0);
    if (chapterIndex > 0) {
      for (let index = tasks.length - 1; index >= 0; index -= 1) {
        const task = tasks[index];
        const start = Number(task?.start_chapter_index ?? 0);
        const requested = Number(task?.requested_chapter_count ?? 0);
        const current = Number(task?.current_chapter_index ?? start);
        const endExclusive = Math.min(current, start + requested);
        if (start > 0 && requested > 0 && start <= chapterIndex && chapterIndex < endExclusive) {
          return task;
        }
      }
    }
    for (let index = tasks.length - 1; index >= 0; index -= 1) {
      const task = tasks[index];
      if (task?.chapter_ids?.includes(chapterId)) {
        return task;
      }
    }
    return null;
  }

  function getNextChapterIndex(project: any) {
    const chapters = Array.isArray(project?.chapters) ? project.chapters : [];
    const latestChapterIndex = chapters.reduce((maxIndex: number, chapter: any) => {
      const chapterIndex = Number(chapter?.chapter_index ?? 0);
      return Number.isFinite(chapterIndex) && chapterIndex > maxIndex ? chapterIndex : maxIndex;
    }, 0);
    return latestChapterIndex + 1;
  }

  function findPreferredChapter(taskPayload: any) {
    if (!taskPayload?.task || !taskPayload?.chapters?.length) {
      return null;
    }
    if (taskPayload.task.status === "waiting_user_confirm") {
      return taskPayload.chapters.find((chapter: any) => !chapter.confirmed_by_user) ?? taskPayload.chapters[taskPayload.chapters.length - 1];
    }
    return taskPayload.chapters[taskPayload.chapters.length - 1];
  }

  async function loadCreatorSupportData() {
    const [projectList, quota, availableGenres] = await Promise.all([
      listProjects(),
      getQuotas(),
      listGenres(),
    ]);
    setProjects(projectList);
    setQuotaData(quota);
    setGenres(availableGenres);
    setForm((current) => {
      const nextGenres = ensureGenreOptions(availableGenres, current.genre);
      const fallbackGenre = nextGenres[0]?.value ?? current.genre;
      const normalizedSelected = (current.genres ?? []).filter((item) => nextGenres.some((genre) => genre.value === item));
      const resolvedGenres = normalizedSelected.length ? normalizedSelected : [fallbackGenre];
      return nextGenres.some((item) => item.value === current.genre)
        ? { ...current, genres: resolvedGenres, genre: resolvedGenres[0] }
        : { ...current, genre: fallbackGenre, genres: resolvedGenres };
    });
  }

  async function loadAdminSupportData() {
    const [memberships, users, orders, safety, logs, genreConfigs] = await Promise.all([
      getAdminMemberships(quotaAdjustForm.targetUserId),
      getAdminUsers(),
      getAdminOrders(),
      getAdminSafetyPolicies(),
      getAdminTaskLogs(),
      getAdminGenres(),
    ]);
    setAdminData({
      memberships,
      users,
      orders,
      safety,
      logs,
      genres: genreConfigs,
    });
    setSafetyForm({
      blockedTerms: (safety?.blocked_terms ?? []).join("\n"),
      copyrightNotice: safety?.copyright_notice ?? "",
    });
  }

  async function handleLoadMembershipTarget() {
    setLoading(true);
    setBusyMessage("正在加载目标用户额度...");
    setError("");
    try {
      const memberships = await getAdminMemberships(quotaAdjustForm.targetUserId);
      setAdminData((current: any) => ({ ...current, memberships }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.adminAction);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleAdminCreateUser() {
    if (!adminUserForm.username.trim()) {
      setError("请输入新客户用户名。");
      return;
    }
    setLoading(true);
    setBusyMessage("正在创建客户账号...");
    setError("");
    try {
      await createAdminUser({ username: adminUserForm.username.trim(), password: "11111111", role: "creator" });
      setAdminUserForm(initialAdminUserForm);
      await loadAdminSupportData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.adminAction);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleAdminResetUserPassword(userId: string) {
    if (!window.confirm("确认将该客户密码重置为 11111111 吗？")) {
      return;
    }
    setLoading(true);
    setBusyMessage("正在重置客户密码...");
    setError("");
    try {
      await resetAdminUserPassword(userId);
      await loadAdminSupportData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.adminAction);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  function navigate(nextRoute: Route) {
    setRoute(nextRoute);
    writeRoute(nextRoute);
    setError("");
  }

  useEffect(() => {
    function syncRoute() {
      setRoute(readRoute());
    }
    window.addEventListener("hashchange", syncRoute);
    return () => window.removeEventListener("hashchange", syncRoute);
  }, []);

  useEffect(() => {
    if (!session) {
      if (route !== "/login") {
        navigate("/login");
      }
      return;
    }
    if (isSharedRoute(route)) {
      return;
    }
    if (session.user.role === "creator" && isAdminRoute(route)) {
      navigate(defaultCreatorRoute);
      return;
    }
    if (session.user.role === "admin" && isCreatorRoute(route)) {
      navigate(defaultAdminRoute);
    }
  }, [route, session]);

  useEffect(() => {
    if (!session) {
      return;
    }
    getMe()
      .then((user) => {
        setSession((current) => {
          if (!current) {
            return current;
          }
          const nextSession = { ...current, user };
          persistSession(nextSession);
          return nextSession;
        });
      })
      .catch(() => {
        persistSession(null);
        setSession(null);
        setError("登录状态已失效，请重新登录。");
        navigate("/login");
      });
  }, []);

  useEffect(() => {
    if (!session) {
      return;
    }
    loadCreatorSupportData().catch((caught) => setError(caught instanceof Error ? caught.message : "加载创作数据失败"));
  }, [session]);

  useEffect(() => {
    if (session?.user.role !== "admin") {
      return;
    }
    loadAdminSupportData().catch((caught) => setError(caught instanceof Error ? caught.message : labels.errors.adminAction));
  }, [session]);

  useEffect(() => {
    if (!overlayMessage) {
      setBusyStartedAt(null);
      setBusyElapsedSeconds(0);
      return;
    }
    const startedAt = busyStartedAt ?? Date.now();
    if (busyStartedAt === null) {
      setBusyStartedAt(startedAt);
    }
    setBusyElapsedSeconds(Math.max(1, Math.floor((Date.now() - startedAt) / 1000)));
    const timer = window.setInterval(() => {
      setBusyElapsedSeconds(Math.max(1, Math.floor((Date.now() - startedAt) / 1000)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [busyStartedAt, overlayMessage]);

  useEffect(() => {
    const activePlanId = adminData.memberships?.default_plan_id;
    if (!activePlanId) {
      return;
    }
    setOrderForm((current) => ({ ...current, plan_id: current.plan_id || activePlanId }));
  }, [adminData.memberships]);

  useEffect(() => {
    persistWorkspaceState({ selectedProjectId, selectedTaskId, selectedChapterId });
  }, [selectedChapterId, selectedProjectId, selectedTaskId]);

  useEffect(() => {
    if (!taskData?.chapters) {
      return;
    }
    const nextOutlineEdits: Record<string, OutlineEdit> = {};
    const nextDraftEdits: Record<string, string> = {};
    const nextChapterTitleEdits: Record<string, string> = {};
    taskData.chapters.forEach((chapter: any) => {
      nextChapterTitleEdits[chapter.id] = chapter.title;
      chapter.outline_options.forEach((option: any) => {
        nextOutlineEdits[option.id] = buildOutlineEdit(option);
      });
      const selectedDraft = chapter.drafts.find((draft: any) => draft.selected) ?? chapter.drafts[chapter.drafts.length - 1];
      if (selectedDraft) {
        nextDraftEdits[chapter.id] = selectedDraft.content;
      }
    });
    setOutlineEdits(nextOutlineEdits);
    setChapterTitleEdits(nextChapterTitleEdits);
    setDraftEdits(nextDraftEdits);
  }, [taskData]);

  async function refreshWorkspace(projectId: string, taskId?: string, options?: { preferLatestTask?: boolean; refreshSupportData?: boolean }) {
    const refreshedProject = await getProject(projectId);
    let refreshedTaskData: any = null;
    const preferLatestTask = options?.preferLatestTask ?? true;
    const refreshSupportData = options?.refreshSupportData ?? true;
    setSelectedProjectId(projectId);
    setProjectData(refreshedProject);
    if (taskId) {
      let refreshedTask = await getTask(projectId, taskId);
      if (
        ["queued", "running"].includes(refreshedTask?.task?.status ?? "") &&
        !(refreshedTask?.chapters?.length ?? 0)
      ) {
        await runTask(projectId, taskId);
        refreshedTask = await getTask(projectId, taskId);
      }
      const taskHasChapters = (refreshedTask?.chapters?.length ?? 0) > 0;
      const taskIsActive = ["queued", "running", "waiting_user_confirm"].includes(refreshedTask?.task?.status ?? "");
      if (taskHasChapters || taskIsActive) {
        refreshedTaskData = refreshedTask;
        setSelectedTaskId(taskId);
        setTaskData(refreshedTask);
        const hasSelectedChapter = refreshedTask.chapters?.some((chapter: any) => chapter.id === selectedChapterId);
        const latestChapter = refreshedTask.chapters?.[refreshedTask.chapters.length - 1];
        setSelectedChapterId(hasSelectedChapter ? selectedChapterId : latestChapter?.id ?? "");
      } else {
        setSelectedTaskId("");
        setTaskData(null);
        setSelectedChapterId("");
      }
    } else {
      const activeTask = findActiveTask(refreshedProject.project);
      const latestTaskWithChapters = preferLatestTask
        ? [...(refreshedProject.project.tasks ?? [])]
            .reverse()
            .find((task: any) => (task.chapter_ids?.length ?? 0) > 0)
        : null;
      const preferredTask = activeTask ?? latestTaskWithChapters ?? null;
      console.info("[workspace.refresh]", {
        projectId,
        requestedTaskId: taskId ?? null,
        preferLatestTask,
        activeTaskId: activeTask?.id ?? null,
        latestTaskWithChaptersId: latestTaskWithChapters?.id ?? null,
        projectTaskStates: (refreshedProject.project.tasks ?? []).map((task: any) => ({
          id: task.id,
          status: task.status,
          chapterIds: task.chapter_ids ?? [],
        })),
      });
      if (preferredTask?.id) {
        let refreshedTask = await getTask(projectId, preferredTask.id);
        if (
          ["queued", "running"].includes(refreshedTask?.task?.status ?? "") &&
          !(refreshedTask?.chapters?.length ?? 0)
        ) {
          await runTask(projectId, preferredTask.id);
          refreshedTask = await getTask(projectId, preferredTask.id);
        }
        refreshedTaskData = refreshedTask;
        setSelectedTaskId(preferredTask.id);
        setTaskData(refreshedTask);
        const hasSelectedChapter = refreshedTask.chapters?.some((chapter: any) => chapter.id === selectedChapterId);
        const latestChapter = refreshedTask.chapters?.[refreshedTask.chapters.length - 1];
        setSelectedChapterId(hasSelectedChapter ? selectedChapterId : latestChapter?.id ?? "");
      } else {
        setSelectedTaskId("");
        setTaskData(null);
        setSelectedChapterId("");
      }
    }
    if (refreshSupportData) {
      await loadCreatorSupportData();
    }
    if (refreshSupportData && session?.user.role === "admin") {
      await loadAdminSupportData();
    }
    return { project: refreshedProject, task: refreshedTaskData };
  }

  function syncChapterIntoTaskState(updatedChapter: any) {
    if (!updatedChapter) {
      return;
    }
    setTaskData((current: any) => {
      if (!current?.chapters?.length) {
        return current;
      }
      const nextChapters = current.chapters.map((chapter: any) => (chapter.id === updatedChapter.id ? updatedChapter : chapter));
      return { ...current, chapters: nextChapters };
    });
    setOutlineEdits((current) => {
      const next = { ...current };
      const replacedOptionIds = new Set<string>(
        ((taskData?.chapters ?? []).find((chapter: any) => chapter.id === updatedChapter.id)?.outline_options ?? []).map((option: any) => option.id),
      );
      replacedOptionIds.forEach((optionId) => {
        delete next[optionId];
      });
      (updatedChapter.outline_options ?? []).forEach((option: any) => {
        next[option.id] = buildOutlineEdit(option);
      });
      return next;
    });
    setChapterTitleEdits((current) => ({ ...current, [updatedChapter.id]: updatedChapter.title }));
    setDraftEdits((current) => {
      const selectedDraft =
        updatedChapter.drafts?.find((draft: any) => draft.selected) ??
        updatedChapter.drafts?.[updatedChapter.drafts.length - 1];
      if (!selectedDraft) {
        return current;
      }
      return { ...current, [updatedChapter.id]: selectedDraft.content };
    });
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    if (!authUsername.trim()) {
      setError("请输入用户名。");
      return;
    }
    if (!authPassword.trim()) {
      setError("请输入密码。");
      return;
    }
    if (authMode === "register") {
      if (authPassword.length < 6) {
        setError("密码长度不能少于 6 位。");
        return;
      }
      if (authPassword !== authConfirmPassword) {
        setError("两次输入的密码不一致。");
        return;
      }
    }
    setLoading(true);
    setError("");
    try {
      if (authMode === "register") {
        await register({ username: authUsername.trim(), password: authPassword });
      }
      const nextSession = await login({ username: authUsername.trim(), password: authPassword });
      persistSession(nextSession);
      setSession(nextSession);
      setAuthPassword("");
      setAuthConfirmPassword("");
      navigate(currentRouteForSession(nextSession));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : authMode === "register" ? "注册失败" : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Session cleanup should still proceed if backend logout fails.
    } finally {
      persistSession(null);
      setSession(null);
      setProjects([]);
      setSelectedProjectId("");
      setSelectedTaskId("");
      setSelectedChapterId("");
      setProjectData(null);
      setTaskData(null);
      setRunningTask(false);
      setActiveActionKey("");
      setBusyMessage("");
      setChapterTitleEdits({});
      setEditingChapterTitles({});
      setChapterFeedbacks({});
      setChapterTransformInstructions({});
      setChapterTransformParagraphs({});
      setChapterTransformResults({});
      setAdminData({ memberships: null, users: [], orders: [], safety: null, logs: [] });
      navigate("/login");
    }
  }

  async function handleChangePassword(event: FormEvent) {
    event.preventDefault();
    if (!passwordForm.currentPassword.trim()) {
      setError("请输入当前密码。");
      return;
    }
    if (passwordForm.newPassword.length < 6) {
      setError("新密码长度不能少于 6 位。");
      return;
    }
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setError("两次输入的新密码不一致。");
      return;
    }
    setLoading(true);
    setBusyMessage("正在修改密码...");
    setError("");
    try {
      const nextSession = await changePassword({
        current_password: passwordForm.currentPassword,
        new_password: passwordForm.newPassword,
      });
      persistSession(nextSession);
      setSession(nextSession);
      setPasswordForm(initialPasswordForm);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "修改密码失败");
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleCreateProject(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setBusyMessage("正在创建项目...");
    setError("");
    try {
      const project = await createProject({
        title: form.title,
        genre: form.genre,
        genres: form.genres,
        length_type: form.length_type,
        template_id: form.template_id,
        summary: form.summary,
        character_cards: splitLines(form.character_cards),
        world_rules: splitLines(form.world_rules),
        event_summary: splitLines(form.event_summary),
        story_beats: parseStoryBeatsInput(form.story_beats),
        mode_default: form.mode_default,
      });
      await refreshWorkspace(project.id);
      setTaskData(null);
      setOutlineEdits({});
      setChapterTitleEdits({});
      setEditingChapterTitles({});
      setDraftEdits({});
      setChapterTransformInstructions({});
      setChapterTransformParagraphs({});
      setChapterTransformResults({});
      navigate("/projects/detail");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.createProject);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleGenerateProjectFoundation() {
    if (!form.title.trim()) {
      setError("请先输入项目标题。");
      return;
    }
    setLoading(true);
    setBusyMessage("正在生成项目基础设定...");
    setRestoredFoundationBusyMessage("正在生成项目基础设定...");
    persistFoundationBusyMessage("正在生成项目基础设定...");
    setError("");
    try {
      const task = await generateProjectFoundation({
        title: form.title,
        genre: form.genre,
        genres: form.genres,
        length_type: form.length_type,
        template_id: form.template_id,
        summary: form.summary,
        character_cards: splitLines(form.character_cards),
        world_rules: splitLines(form.world_rules),
        event_summary: splitLines(form.event_summary),
      });
      setFoundationTaskId(task.task_id);
      persistFoundationTaskId(task.task_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "生成项目基础设定失败");
      setRestoredFoundationBusyMessage("");
      persistFoundationBusyMessage("");
      setFoundationTaskId("");
      persistFoundationTaskId("");
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  useEffect(() => {
    if (!foundationTaskId || !session || session.user.role !== "creator") {
      return;
    }
    let stopped = false;
    const timer = window.setInterval(async () => {
      try {
        const task = await getProjectFoundationTask(foundationTaskId);
        if (stopped) {
          return;
        }
        if (task.status === "completed") {
          setForm((current) => ({
            ...current,
            summary: task.result?.summary?.trim() ? task.result.summary : current.summary,
            character_cards:
              task.result?.character_cards && task.result.character_cards.length > 0
                ? task.result.character_cards.join("\n")
                : current.character_cards,
            world_rules:
              task.result?.world_rules && task.result.world_rules.length > 0
                ? task.result.world_rules.join("\n")
                : current.world_rules,
            event_summary:
              task.result?.event_summary && task.result.event_summary.length > 0
                ? task.result.event_summary.join("\n")
                : current.event_summary,
            story_beats:
              task.result?.story_beats && task.result.story_beats.length > 0
                ? storyBeatsToText(task.result.story_beats)
                : current.story_beats,
          }));
          setBusyProgressStage("completed");
          setBusyProgressMessage(task.progress_message ?? "");
          setRestoredFoundationBusyMessage("");
          persistFoundationBusyMessage("");
          setFoundationTaskId("");
          persistFoundationTaskId("");
          window.clearInterval(timer);
          return;
        }
        if (task.progress_stage || task.progress_message) {
          setBusyProgressStage(task.progress_stage ?? "");
          setBusyProgressMessage(task.progress_message ?? "");
        }
        if (task.status === "failed") {
          setError(task.error_message || "生成项目基础设定失败");
          setBusyProgressStage("failed");
          setBusyProgressMessage(task.progress_message ?? task.error_message ?? "");
          setRestoredFoundationBusyMessage("");
          persistFoundationBusyMessage("");
          setFoundationTaskId("");
          persistFoundationTaskId("");
          window.clearInterval(timer);
        }
      } catch (caught) {
        if (stopped) {
          return;
        }
        setError(caught instanceof Error ? caught.message : "获取基础设定任务状态失败");
        setRestoredFoundationBusyMessage("");
        persistFoundationBusyMessage("");
        setFoundationTaskId("");
        persistFoundationTaskId("");
        window.clearInterval(timer);
      }
    }, 1500);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [foundationTaskId, session]);

  async function handleRunTask() {
    if (!projectData?.project?.id) {
      setError(labels.states.noProject);
      return;
    }
    const activeTask = findActiveTask(projectData.project);
    if (activeTask?.id) {
      setLoading(true);
      setBusyMessage("正在返回当前续写任务...");
      setError("");
      try {
        const refreshed = await refreshWorkspace(projectData.project.id, activeTask.id);
        const chapterToOpen = findPreferredChapter(refreshed.task);
        if (chapterToOpen?.id) {
          await handleOpenChapter(chapterToOpen.id);
        } else {
          setError(
            refreshed.task?.task?.status === "queued" || refreshed.task?.task?.status === "running"
              ? "当前任务正在处理中，暂时还没有可打开的章节。"
              : "当前任务已加载，但暂时没有可查看的章节。"
          );
          navigate("/projects/detail");
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : labels.errors.runTask);
      } finally {
        setLoading(false);
        setBusyMessage("");
      }
      return;
    }
    setRunningTask(true);
    setLoading(true);
    setBusyMessage("正在创建并执行续写任务...");
    setError("");
    try {
      const nextChapterIndex = getNextChapterIndex(projectData.project);
      const task = await createTask(projectData.project.id, {
        mode: taskMode,
        chapter_count: chapterCount,
        start_chapter_index: chapterCount > (projectData.project.chapters?.length ?? 0) ? nextChapterIndex : 1,
      });
      setSelectedTaskId(task.id);
      let stopped = false;
      const poller = window.setInterval(async () => {
        if (stopped) {
          return;
        }
        try {
          const current = await getTask(projectData.project.id, task.id);
          if (stopped) {
            return;
          }
          setBusyProgressStage(current.task?.progress_stage ?? "");
          setBusyProgressMessage(current.task?.progress_message ?? "");
        } catch {
          // Ignore polling failures here; the main request result still drives success/failure.
        }
      }, 1200);
      const result = await runTask(projectData.project.id, task.id);
      stopped = true;
      window.clearInterval(poller);
      await refreshWorkspace(projectData.project.id, result.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.runTask);
    } finally {
      setRunningTask(false);
      setLoading(false);
      setBusyMessage("");
      setBusyProgressStage("");
      setBusyProgressMessage("");
    }
  }

  async function handleClearActiveTask() {
    if (!projectData?.project?.id) {
      setError(labels.states.noProject);
      return;
    }
    if (!window.confirm("确认清理当前进行中的任务吗？这会移除该任务及其关联章节，然后你可以重新生成。")) {
      return;
    }
    setLoading(true);
    setBusyMessage("正在清理当前任务...");
    setError("");
    try {
      await clearActiveTask(projectData.project.id);
      setSelectedTaskId("");
      setSelectedChapterId("");
      setTaskData(null);
      await refreshWorkspace(projectData.project.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "清理当前任务失败");
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleConfirm(chapterId: string) {
    if (!projectData?.project?.id) {
      return;
    }
    const ownerTask = findTaskForChapter(projectData.project, chapterId);
    const taskIdForPolling = ownerTask?.id ?? taskData?.task?.id ?? "";
    setActiveActionKey(`chapter-confirm:${chapterId}`);
    setLoading(true);
    setBusyMessage("正在确认本章并继续推进后续章节...");
    setChapterFeedbacks((current) => ({
      ...current,
      [chapterId]: { tone: "working", message: "正在确认本章，系统会继续生成后续章节，并实时刷新进度。" },
    }));
    setError("");
    let stopped = false;
    const progressPoller =
      taskIdForPolling
        ? window.setInterval(async () => {
            if (stopped) {
              return;
            }
            try {
              const current = await getTask(projectData.project.id, taskIdForPolling);
              if (stopped) {
                return;
              }
              setBusyProgressStage(current.task?.progress_stage ?? "");
              setBusyProgressMessage(current.task?.progress_message ?? "");
            } catch {
              // Ignore polling failures while the confirmation request is still in flight.
            }
          }, 1200)
        : null;
    try {
      const result = await confirmChapter(projectData.project.id, chapterId);
      stopped = true;
      if (progressPoller !== null) {
        window.clearInterval(progressPoller);
      }
      const refreshed = await refreshWorkspace(projectData.project.id, result.id);
      const refreshedStatus = refreshed.task?.task?.status ?? "";
      const refreshedStage = refreshed.task?.task?.progress_stage ?? "";
      const refreshedMessage = refreshed.task?.task?.progress_message ?? "";
      const nextChapter = findPreferredChapter(refreshed.task);
      if (["queued", "running"].includes(refreshedStatus)) {
        setChapterFeedbacks((current) => ({
          ...current,
          [chapterId]: {
            tone: "success",
            message:
              refreshedMessage ||
              (nextChapter?.chapter_index
                ? `本章已确认，系统正在继续生成第 ${nextChapter.chapter_index} 章。`
                : "本章已确认，系统正在继续生成后续章节。"),
          },
        }));
        setBusyProgressStage(refreshedStage);
        setBusyProgressMessage(refreshedMessage);
      } else if (refreshedStatus === "waiting_user_confirm") {
        if (nextChapter?.id) {
          setNextChapterReadyNotice({
            chapterId: nextChapter.id,
            chapterIndex: nextChapter.chapter_index,
            taskId: refreshed.task?.task?.id ?? result.id,
          });
        }
        setChapterFeedbacks((current) => ({
          ...current,
          [chapterId]: {
            tone: "success",
            message:
              refreshedMessage ||
              (nextChapter?.chapter_index
                ? `本章已确认，第 ${nextChapter.chapter_index} 章已生成，等待人工确认。`
                : "本章已确认，下一章已生成，等待人工确认。"),
          },
        }));
      } else {
        setChapterFeedbacks((current) => ({ ...current, [chapterId]: { tone: "success", message: "本章已确认，界面已刷新到最新状态。" } }));
      }
    } catch (caught) {
      stopped = true;
      if (progressPoller !== null) {
        window.clearInterval(progressPoller);
      }
      setChapterFeedbacks((current) => ({ ...current, [chapterId]: { tone: "error", message: "确认失败，请检查接口返回并重试。" } }));
      setError(caught instanceof Error ? caught.message : labels.errors.confirmChapter);
    } finally {
      stopped = true;
      if (progressPoller !== null) {
        window.clearInterval(progressPoller);
      }
      setLoading(false);
      setActiveActionKey("");
      setBusyMessage("");
    }
  }

  async function handleOutlineAction(chapterId: string, action: "regenerate" | "select" | "save", option?: any) {
    if (!projectData?.project?.id || !taskData?.task?.id) {
      return;
    }
    const actionKey =
      action === "regenerate" ? `outline-regenerate:${chapterId}` : `outline-${action}:${chapterId}:${option?.id ?? ""}`;
    const workingMessage =
      action === "regenerate" ? "正在重生成本章走向..." : action === "select" ? "正在保存选中的走向..." : "正在保存走向修改...";
    const successMessage =
      action === "regenerate" ? "走向已重生成，界面已刷新。" : action === "select" ? "走向已选用，正文可据此继续生成。" : "走向修改已保存。";
    setActiveActionKey(actionKey);
    setLoading(true);
    setBusyMessage(workingMessage);
    setChapterFeedbacks((current) => ({ ...current, [chapterId]: { tone: "working", message: workingMessage } }));
    setError("");
    try {
      if (action === "regenerate") {
        const userIdea = window.prompt("可选：输入你这次想让 AI 参考的章节想法。留空则按现有设定直接重新生成走向。", "") ?? "";
        const updatedChapter = await regenerateChapterOutlines(projectData.project.id, chapterId, userIdea.trim());
        syncChapterIntoTaskState(updatedChapter);
      } else if (action === "select" && option) {
        const updatedChapter = await selectOutlineOption(projectData.project.id, chapterId, option.id);
        syncChapterIntoTaskState(updatedChapter);
      } else if (action === "save" && option) {
        const updatedChapter = await updateOutlineOption(projectData.project.id, chapterId, option.id, outlineEdits[option.id]);
        syncChapterIntoTaskState(updatedChapter);
      }
      await refreshWorkspace(projectData.project.id, taskData.task.id, { refreshSupportData: false });
      setChapterFeedbacks((current) => ({ ...current, [chapterId]: { tone: "success", message: successMessage } }));
    } catch (caught) {
      setChapterFeedbacks((current) => ({ ...current, [chapterId]: { tone: "error", message: "走向操作失败，请检查接口返回并重试。" } }));
      setError(caught instanceof Error ? caught.message : labels.errors.outlineAction);
    } finally {
      setLoading(false);
      setActiveActionKey("");
      setBusyMessage("");
    }
  }

  async function handleDraftAction(chapter: any, action: "regenerate" | "save") {
    if (!projectData?.project?.id || !taskData?.task?.id) {
      return;
    }
    const actionKey = action === "regenerate" ? `draft-regenerate:${chapter.id}` : `draft-save:${chapter.id}`;
    const workingMessage = action === "regenerate" ? "正在重生成正文..." : "正在保存正文修改...";
    const successMessage = action === "regenerate" ? "正文已重生成，界面已刷新。" : "正文修改已保存。";
    setActiveActionKey(actionKey);
    setLoading(true);
    setBusyMessage(workingMessage);
    setChapterFeedbacks((current) => ({ ...current, [chapter.id]: { tone: "working", message: workingMessage } }));
    setError("");
    try {
      const selectedDraft = chapter.drafts.find((draft: any) => draft.selected) ?? chapter.drafts[chapter.drafts.length - 1];
      if (action === "regenerate") {
        await regenerateChapterDraft(projectData.project.id, chapter.id);
      } else if (selectedDraft) {
        await updateChapterDraft(projectData.project.id, chapter.id, selectedDraft.id, draftEdits[chapter.id] ?? selectedDraft.content);
      }
      await refreshWorkspace(projectData.project.id, taskData.task.id, { refreshSupportData: false });
      setChapterFeedbacks((current) => ({ ...current, [chapter.id]: { tone: "success", message: successMessage } }));
    } catch (caught) {
      setChapterFeedbacks((current) => ({ ...current, [chapter.id]: { tone: "error", message: "正文操作失败，请检查接口返回并重试。" } }));
      setError(caught instanceof Error ? caught.message : labels.errors.draftAction);
    } finally {
      setLoading(false);
      setActiveActionKey("");
      setBusyMessage("");
    }
  }

  async function handleChapterTitleSave(chapterId: string) {
    if (!projectData?.project?.id || !taskData?.task?.id) {
      return;
    }
    setActiveActionKey(`chapter-title-save:${chapterId}`);
    setLoading(true);
    setBusyMessage("正在保存章节名称...");
    setChapterFeedbacks((current) => ({ ...current, [chapterId]: { tone: "working", message: "正在保存章节名称..." } }));
    setError("");
    try {
      await updateChapter(projectData.project.id, chapterId, chapterTitleEdits[chapterId] ?? "");
      await refreshWorkspace(projectData.project.id, taskData.task.id, { refreshSupportData: false });
      setEditingChapterTitles((current) => ({ ...current, [chapterId]: false }));
      setChapterFeedbacks((current) => ({ ...current, [chapterId]: { tone: "success", message: "章节名称已保存。" } }));
    } catch (caught) {
      setChapterFeedbacks((current) => ({ ...current, [chapterId]: { tone: "error", message: "章节名称保存失败，请重试。" } }));
      setError(caught instanceof Error ? caught.message : "章节名称保存失败");
    } finally {
      setLoading(false);
      setActiveActionKey("");
      setBusyMessage("");
    }
  }

  async function handleDeleteChapter(chapterId: string) {
    if (!projectData?.project?.id) {
      return;
    }
    if (!window.confirm("确认删除这个章节吗？此操作会移除该章节及其当前详情视图。")) {
      return;
    }
    setActiveActionKey(`chapter-delete:${chapterId}`);
    setLoading(true);
    setBusyMessage("正在删除章节...");
    setError("");
    try {
      await deleteChapter(projectData.project.id, chapterId);
      if (selectedChapterId === chapterId) {
        setSelectedChapterId("");
      }
      setSelectedTaskId("");
      setTaskData(null);
      await refreshWorkspace(projectData.project.id, undefined, { preferLatestTask: false });
      if (selectedChapterId === chapterId) {
        navigate("/projects/detail");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除章节失败");
    } finally {
      setLoading(false);
      setActiveActionKey("");
      setBusyMessage("");
    }
  }

  async function handleChapterTransform(chapter: any, action: "rewrite" | "expand" | "remove") {
    if (!projectData?.project?.id) {
      return;
    }
    const selectedDraft = chapter.drafts.find((draft: any) => draft.selected) ?? chapter.drafts[chapter.drafts.length - 1];
    const chapterContent = draftEdits[chapter.id] ?? selectedDraft?.content ?? "";
    const instruction = chapterTransformInstructions[chapter.id]?.trim();
    const paragraph = chapterTransformParagraphs[chapter.id]?.trim();
    if (!instruction) {
      setError("请输入本章重写、拓写或去除要求。");
      return;
    }
    if (action === "remove" && !paragraph) {
      setError("去除段落时必须填写目标段落。");
      return;
    }
    const actionKey = `chapter-transform:${action}:${chapter.id}`;
    const workingMessage =
      action === "rewrite" ? "正在整章重写..." : action === "expand" ? "正在整章拓写..." : "正在去除段落...";
    const successMessage =
      action === "rewrite"
        ? "整章重写已完成，正文编辑区已同步更新。"
        : action === "expand"
          ? "整章拓写已完成，正文编辑区已同步更新。"
          : "目标段落已去除，正文编辑区已同步更新。";
    setActiveActionKey(actionKey);
    setLoading(true);
    setBusyMessage(workingMessage);
    setChapterFeedbacks((current) => ({ ...current, [chapter.id]: { tone: "working", message: workingMessage } }));
    setError("");
    try {
      const result =
        action === "rewrite"
          ? await rewriteChapter(projectData.project.id, chapter.id, instruction, chapterContent, paragraph)
          : action === "expand"
            ? await expandChapter(projectData.project.id, chapter.id, instruction, chapterContent, paragraph)
            : await removeChapterParagraph(projectData.project.id, chapter.id, instruction, chapterContent, paragraph ?? "");
      setChapterTransformResults((current) => ({ ...current, [chapter.id]: result }));
      if (result.chapter_updated) {
        setDraftEdits((current) => ({ ...current, [chapter.id]: result.chapter_updated }));
      }
      setChapterFeedbacks((current) => ({ ...current, [chapter.id]: { tone: "success", message: successMessage } }));
    } catch (caught) {
      setChapterFeedbacks((current) => ({ ...current, [chapter.id]: { tone: "error", message: "章节处理失败，请检查接口返回并重试。" } }));
      setError(caught instanceof Error ? caught.message : "章节处理失败");
    } finally {
      setLoading(false);
      setActiveActionKey("");
      setBusyMessage("");
    }
  }

  async function handleAdjustQuota() {
    setLoading(true);
    setBusyMessage("正在调整额度...");
    setError("");
    try {
      await adjustAdminQuota(quotaAdjustForm.dailyDelta, quotaAdjustForm.monthlyDelta, quotaAdjustForm.bonusDelta, quotaAdjustForm.targetUserId);
      setQuotaAdjustForm((current) => ({ ...current, dailyDelta: 0, monthlyDelta: 0, bonusDelta: 0 }));
      await loadAdminSupportData();
      await loadCreatorSupportData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.adminAction);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handlePlanSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setBusyMessage(editingPlanId ? "正在保存套餐..." : "正在创建套餐...");
    setError("");
    try {
      if (editingPlanId) {
        await updateAdminMembershipPlan(editingPlanId, planForm);
      } else {
        await createAdminMembershipPlan(planForm);
      }
      setPlanForm(initialPlanForm);
      setEditingPlanId("");
      setPlanModalOpen(false);
      await loadAdminSupportData();
      await loadCreatorSupportData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.adminAction);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleActivatePlan(planId: string) {
    setLoading(true);
      setBusyMessage("正在切换默认套餐...");
    setError("");
    try {
      await activateAdminMembershipPlan(planId);
      await loadAdminSupportData();
      await loadCreatorSupportData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.adminAction);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleOrderSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setBusyMessage(editingOrderId ? "正在保存订单..." : "正在创建订单...");
    setError("");
    try {
      if (editingOrderId) {
        await updateAdminOrder(editingOrderId, orderForm);
      } else {
        await createAdminOrder(orderForm);
      }
      setOrderForm({
        ...initialOrderForm,
        plan_id: adminData.memberships?.default_plan_id ?? initialOrderForm.plan_id,
      });
      setEditingOrderId("");
      await loadAdminSupportData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.adminAction);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleUpdateSafetyPolicy() {
    if (!adminData.safety?.id) {
      return;
    }
    setLoading(true);
    setBusyMessage("正在保存安全策略...");
    setError("");
    try {
      await updateAdminSafetyPolicy(adminData.safety.id, {
        blocked_terms: splitLines(safetyForm.blockedTerms),
        copyright_notice: safetyForm.copyrightNotice.trim(),
      });
      await loadAdminSupportData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.adminAction);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleSaveGenreConfig() {
    if (!genreAdminForm.value.trim()) {
      setError("请输入题材标识。");
      return;
    }
    setLoading(true);
    setBusyMessage("正在保存题材规则...");
    setError("");
    try {
      await updateAdminGenre(genreAdminForm.value.trim(), {
        label: genreAdminForm.label.trim() || genreAdminForm.value.trim(),
        required_any: splitLines(genreAdminForm.required_any),
        forbidden_any: splitLines(genreAdminForm.forbidden_any),
      });
      setGenreAdminForm(initialGenreAdminForm);
      await loadAdminSupportData();
      await loadCreatorSupportData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : labels.errors.adminAction);
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleOpenProject(projectId: string) {
    setLoading(true);
    setBusyMessage("正在加载项目...");
    setError("");
    try {
      await refreshWorkspace(projectId);
      navigate("/projects/detail");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加载项目失败");
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleDeleteProject(project: any) {
    if (!project?.id) {
      return;
    }
    if (!window.confirm(`确认删除项目《${project.title}》吗？该操作会删除项目、章节、任务与结构化记忆。`)) {
      return;
    }
    const confirmationText = window.prompt(`请输入项目名“${project.title}”以确认删除`);
    if (confirmationText !== project.title) {
      setError("项目名确认不匹配，已取消删除。");
      return;
    }
    setLoading(true);
    setBusyMessage("正在删除项目...");
    setError("");
    try {
      await deleteProject(project.id);
      if (selectedProjectId === project.id) {
        setSelectedProjectId("");
        setSelectedTaskId("");
        setSelectedChapterId("");
        setProjectData(null);
        setTaskData(null);
      }
      await loadCreatorSupportData();
      navigate("/projects");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除项目失败");
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  async function handleOpenChapter(chapterId: string) {
    if (!projectData?.project?.id) {
      setError(labels.states.noProject);
      return;
    }
    setLoading(true);
    setBusyMessage("正在打开章节...");
    setError("");
    try {
      const detail = await getChapterDetail(projectData.project.id, chapterId);
      if (detail?.chapter) {
        setChapterDetailData({
          task: detail.task ?? null,
          chapters: [detail.chapter],
          memory: detail.memory ?? projectData.project.memory ?? null,
        });
      } else {
        setChapterDetailData(null);
      }
      if (detail?.task?.id) {
        await refreshWorkspace(projectData.project.id, detail.task.id);
      } else if (!taskData?.chapters?.some((chapter: any) => chapter.id === chapterId)) {
        await refreshWorkspace(projectData.project.id);
      }
      setSelectedChapterId(chapterId);
      if (nextChapterReadyNotice?.chapterId === chapterId) {
        setNextChapterReadyNotice(null);
      }
      navigate("/projects/chapter");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "打开章节失败");
    } finally {
      setLoading(false);
      setBusyMessage("");
    }
  }

  useEffect(() => {
    if (!session || session.user.role !== "creator" || !selectedProjectId) {
      return;
    }
    refreshWorkspace(selectedProjectId, selectedTaskId || undefined).catch((caught) => {
      setSelectedTaskId("");
      setSelectedChapterId("");
      setChapterDetailData(null);
      setProjectData(null);
      setTaskData(null);
      setError(caught instanceof Error ? caught.message : "恢复项目上下文失败");
      if (route !== "/projects") {
        navigate("/projects");
      }
    });
  }, [session]);

  useEffect(() => {
    if (route !== "/projects/chapter" || !projectData?.project || !selectedProjectId || !selectedChapterId) {
      return;
    }
    if (taskData?.chapters?.some((chapter: any) => chapter.id === selectedChapterId)) {
      return;
    }
    const ownerTask = findTaskForChapter(projectData.project, selectedChapterId);
    if (!ownerTask?.id || ownerTask.id === selectedTaskId) {
      return;
    }
    refreshWorkspace(selectedProjectId, ownerTask.id).catch((caught) => {
      setError(caught instanceof Error ? caught.message : "加载章节详情失败");
    });
  }, [projectData, route, selectedChapterId, selectedProjectId, selectedTaskId, taskData]);

  if (!session || route === "/login") {
    return (
      <LoginPage
        mode={authMode}
        username={authUsername}
        password={authPassword}
        confirmPassword={authConfirmPassword}
        loading={loading}
        error={error}
        onModeChange={setAuthMode}
        onUsernameChange={setAuthUsername}
        onPasswordChange={setAuthPassword}
        onConfirmPasswordChange={setAuthConfirmPassword}
        onSubmit={handleLogin}
      />
    );
  }

  const selectedChapterTaskData =
    selectedChapterId
      ? (() => {
          if (taskData?.chapters?.length) {
            const chapters = taskData.chapters.filter((chapter: any) => chapter.id === selectedChapterId);
            if (chapters.length) {
              return { ...taskData, chapters };
            }
          }
          if (chapterDetailData?.chapters?.some((chapter: any) => chapter.id === selectedChapterId)) {
            return chapterDetailData;
          }
          return null;
        })()
      : null;
  const hasActiveTask = Boolean(projectData?.project ? findActiveTask(projectData.project) : null);

  if (session.user.role === "creator") {
    return (
      <AppShell
        title="创作区"
        subtitle="项目、章节与模板拆分为独立页面，减少信息混杂。"
        session={session}
        route={route}
        navItems={[
          { route: "/projects", label: "项目列表" },
          { route: "/projects/detail", label: "项目详情" },
          { route: "/projects/chapter", label: "章节详情" },
          { route: "/account/security", label: "账号安全" },
        ]}
        onNavigate={navigate}
        onLogout={handleLogout}
        passwordForm={passwordForm}
        passwordLoading={loading && busyMessage === "正在修改密码..."}
        onPasswordFormChange={setPasswordForm}
        onPasswordSubmit={handleChangePassword}
      >
        <BusyOverlay
          visible={Boolean(overlayMessage)}
          title={overlayMessage || "正在处理"}
          detail={overlayStageDetail ? `${overlayStageDetail}。${overlayDetail}` : overlayDetail}
          elapsedSeconds={busyElapsedSeconds}
        />
        {nextChapterReadyNotice && projectData?.project?.id ? (
          <div className="panel next-chapter-ready-banner">
            <div>
              <strong>章节生成完毕</strong>
              <p>第 {nextChapterReadyNotice.chapterIndex} 章已生成，可以直接跳转去确认正文。</p>
            </div>
            <div className="inline">
              <button
                type="button"
                onClick={() => {
                  handleOpenChapter(nextChapterReadyNotice.chapterId).catch(() => {
                    // Error handling already happens in handleOpenChapter.
                  });
                }}
              >
                打开第 {nextChapterReadyNotice.chapterIndex} 章
              </button>
              <button type="button" className="ghost-button" onClick={() => setNextChapterReadyNotice(null)}>
                稍后
              </button>
            </div>
          </div>
        ) : null}
        {loading && busyMessage ? <div className="panel busy-banner">{busyMessage}</div> : null}
        {!loading && restoredFoundationBusyMessage ? <div className="panel busy-banner">{restoredFoundationBusyMessage}</div> : null}
        {error ? <div className="panel error-banner">{error}</div> : null}
        {route === "/projects" ? (
          <>
            <ProjectSetupPanel
              form={form}
              genres={ensureGenreOptions(genres, form.genre)}
              loading={loading}
              onChange={setForm}
              onGenerateFoundation={handleGenerateProjectFoundation}
              onSubmit={handleCreateProject}
            />
            <ProjectListPage
              projects={projects}
              genres={genres}
              selectedProjectId={selectedProjectId}
              loading={loading}
              onOpenProject={handleOpenProject}
              onDeleteProject={handleDeleteProject}
            />
          </>
        ) : null}
        {route === "/projects/detail" ? (
          <ProjectDetailPage
            projectData={projectData}
            taskData={taskData}
            quotaData={quotaData}
            genres={ensureGenreOptions(genres, projectData?.project?.genre ?? "")}
            taskMode={taskMode}
            chapterCount={chapterCount}
            loading={loading}
            runningTask={runningTask}
            hasActiveTask={hasActiveTask}
            onModeChange={setTaskMode}
            onChapterCountChange={setChapterCount}
            onRunTask={handleRunTask}
            onClearActiveTask={handleClearActiveTask}
            onOpenChapter={handleOpenChapter}
            onDeleteProject={handleDeleteProject}
          />
        ) : null}
        {route === "/projects/chapter" ? (
          <>
            <section className="panel">
              <div className="section-title-row">
                <h2>章节详情</h2>
                <button onClick={() => navigate("/projects/detail")}>返回项目详情</button>
              </div>
            </section>
            {selectedChapterTaskData ? (
              <ChapterResultsPanel
                taskData={selectedChapterTaskData}
                loading={loading}
                activeActionKey={activeActionKey}
                chapterTitleEdits={chapterTitleEdits}
                editingChapterTitles={editingChapterTitles}
                chapterFeedbacks={chapterFeedbacks}
                draftEdits={draftEdits}
                outlineEdits={outlineEdits}
                chapterTransformInstructions={chapterTransformInstructions}
                chapterTransformParagraphs={chapterTransformParagraphs}
                chapterTransformResults={chapterTransformResults}
                onChapterTitleChange={(chapterId, value) => setChapterTitleEdits((current) => ({ ...current, [chapterId]: value }))}
                onChapterTitleEditingChange={(chapterId, value) =>
                  setEditingChapterTitles((current) => ({ ...current, [chapterId]: value }))
                }
                onSaveChapterTitle={handleChapterTitleSave}
                onOutlineEdit={(optionId, value) => setOutlineEdits((current) => ({ ...current, [optionId]: value }))}
                onDraftEdit={(chapterId, value) => setDraftEdits((current) => ({ ...current, [chapterId]: value }))}
                onChapterTransformInstructionChange={(chapterId, value) =>
                  setChapterTransformInstructions((current) => ({ ...current, [chapterId]: value }))
                }
                onChapterTransformParagraphChange={(chapterId, value) =>
                  setChapterTransformParagraphs((current) => ({ ...current, [chapterId]: value }))
                }
                onConfirm={handleConfirm}
                onDeleteChapter={handleDeleteChapter}
                onOutlineAction={handleOutlineAction}
                onDraftAction={handleDraftAction}
                onChapterTransform={handleChapterTransform}
              />
            ) : (
              <section className="panel">
                <p>请先从项目详情打开一个章节。</p>
              </section>
            )}
          </>
        ) : null}
        {route === "/account/security" ? (
          <AccountSecurityPage
            passwordForm={passwordForm}
            loading={loading && busyMessage === "正在修改密码..."}
            onPasswordFormChange={setPasswordForm}
            onPasswordSubmit={handleChangePassword}
          />
        ) : null}
      </AppShell>
    );
  }

  return (
    <AppShell
      title="后台管理"
      subtitle="模板审核、套餐、订单、安全策略与日志相互隔离，避免与创作工作台混杂。"
      session={session}
      route={route}
      navItems={[
        { route: "/admin/users", label: "账号管理" },
        { route: "/admin/memberships", label: "套餐与额度" },
        { route: "/admin/orders", label: "订单管理" },
        { route: "/admin/genres", label: "题材规则" },
        { route: "/admin/safety", label: "安全策略" },
        { route: "/admin/logs", label: "任务日志" },
        { route: "/account/security", label: "账号安全" },
      ]}
      onNavigate={navigate}
      onLogout={handleLogout}
      passwordForm={passwordForm}
      passwordLoading={loading && busyMessage === "正在修改密码..."}
      onPasswordFormChange={setPasswordForm}
      onPasswordSubmit={handleChangePassword}
    >
      <BusyOverlay
        visible={Boolean(overlayMessage)}
        title={overlayMessage || "正在处理"}
        detail={overlayStageDetail ? `${overlayStageDetail}。${overlayDetail}` : overlayDetail}
        elapsedSeconds={busyElapsedSeconds}
      />
      {loading && busyMessage ? <div className="panel busy-banner">{busyMessage}</div> : null}
      {error ? <div className="panel error-banner">{error}</div> : null}
      {route === "/admin/users" ? (
        <AdminUsersPage
          users={adminData.users}
          adminUserForm={adminUserForm}
          loading={loading}
          onAdminUserFormChange={setAdminUserForm}
          onCreateUser={handleAdminCreateUser}
          onResetUserPassword={handleAdminResetUserPassword}
          onSetMembershipTarget={(userId) => {
            setQuotaAdjustForm((current) => ({ ...current, targetUserId: userId }));
            navigate("/admin/memberships");
          }}
        />
      ) : null}
      {route === "/admin/memberships" ? (
        <AdminMembershipPage
          memberships={adminData.memberships}
          users={adminData.users}
          quotaAdjustForm={quotaAdjustForm}
          planForm={planForm}
          editingPlanId={editingPlanId}
          planModalOpen={planModalOpen}
          loading={loading}
          onQuotaChange={setQuotaAdjustForm}
          onMembershipTargetChange={(targetUserId) => setQuotaAdjustForm((current) => ({ ...current, targetUserId }))}
          onLoadMembershipTarget={handleLoadMembershipTarget}
          onPlanFormChange={setPlanForm}
          onAdjustQuota={handleAdjustQuota}
          onPlanSubmit={handlePlanSubmit}
          onEditPlan={(plan) => {
            setEditingPlanId(plan.id);
            setPlanForm({
              name: plan.name,
              daily_free_chapters: plan.daily_free_chapters,
              monthly_free_chapters: plan.monthly_free_chapters,
              description: plan.description ?? "",
            });
            setPlanModalOpen(true);
          }}
          onCreatePlan={() => {
            setEditingPlanId("");
            setPlanForm(initialPlanForm);
            setPlanModalOpen(true);
          }}
          onClosePlanModal={() => {
            setPlanModalOpen(false);
            setEditingPlanId("");
            setPlanForm(initialPlanForm);
          }}
          onActivatePlan={handleActivatePlan}
        />
      ) : null}
      {route === "/admin/orders" ? (
        <AdminOrdersPage
          memberships={adminData.memberships}
          orders={adminData.orders}
          orderForm={orderForm}
          editingOrderId={editingOrderId}
          loading={loading}
          onOrderFormChange={setOrderForm}
          onOrderSubmit={handleOrderSubmit}
          onEditOrder={(order) => {
            setEditingOrderId(order.id);
            setOrderForm({
              plan_id: order.plan_id,
              amount: order.amount,
              status: order.status,
              note: order.note ?? "",
            });
          }}
        />
      ) : null}
      {route === "/admin/genres" ? (
        <AdminGenrePage
          genres={adminData.genres ?? []}
          form={genreAdminForm}
          loading={loading}
          onFormChange={setGenreAdminForm}
          onSave={handleSaveGenreConfig}
          onEdit={(genre) =>
            setGenreAdminForm({
              value: genre.value,
              label: genre.label,
              required_any: (genre.required_any ?? []).join("\n"),
              forbidden_any: (genre.forbidden_any ?? []).join("\n"),
            })
          }
        />
      ) : null}
      {route === "/admin/safety" ? (
        <AdminSafetyPage safetyForm={safetyForm} loading={loading} onSafetyFormChange={setSafetyForm} onSave={handleUpdateSafetyPolicy} />
      ) : null}
      {route === "/admin/logs" ? <AdminLogsPage logs={adminData.logs} /> : null}
      {route === "/account/security" ? (
        <AccountSecurityPage
          passwordForm={passwordForm}
          loading={loading && busyMessage === "正在修改密码..."}
          onPasswordFormChange={setPasswordForm}
          onPasswordSubmit={handleChangePassword}
        />
      ) : null}
    </AppShell>
  );
}
