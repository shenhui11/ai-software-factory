import { FormEvent, useEffect, useState } from "react";

import "./App.css";
import {
  confirmChapter,
  createProject,
  createTask,
  expandParagraph,
  getProject,
  getTask,
  listTemplates,
  rewriteParagraph,
  runTask,
} from "./api";

type ProjectForm = {
  title: string;
  genre: string;
  length_type: string;
  template_id: string;
  summary: string;
  character_cards: string;
  world_rules: string;
  event_summary: string;
  mode_default: "manual" | "auto";
};

const initialForm: ProjectForm = {
  title: "Moonlit Chronicle",
  genre: "fantasy",
  length_type: "long",
  template_id: "tpl-system-romance",
  summary: "A fallen court mage seeks to restore a shattered kingdom.",
  character_cards: "Lina the mage\nPrince Rowan\nThe masked archivist",
  world_rules: "Magic leaves visible scars\nThe moon archive remembers oaths",
  event_summary: "The kingdom collapsed after the eclipse war",
  mode_default: "manual",
};

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function App() {
  const [form, setForm] = useState<ProjectForm>(initialForm);
  const [projectData, setProjectData] = useState<any>(null);
  const [taskData, setTaskData] = useState<any>(null);
  const [templates, setTemplates] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [taskMode, setTaskMode] = useState<"manual" | "auto">("manual");
  const [chapterCount, setChapterCount] = useState(3);
  const [rewriteResult, setRewriteResult] = useState<any>(null);

  useEffect(() => {
    listTemplates().then(setTemplates).catch(() => undefined);
  }, []);

  async function handleCreateProject(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const project = await createProject({
        title: form.title,
        genre: form.genre,
        length_type: form.length_type,
        template_id: form.template_id,
        summary: form.summary,
        character_cards: splitLines(form.character_cards),
        world_rules: splitLines(form.world_rules),
        event_summary: splitLines(form.event_summary),
        mode_default: form.mode_default,
      });
      const detail = await getProject(project.id);
      setProjectData(detail);
      setTaskData(null);
      setRewriteResult(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to create project");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunTask() {
    if (!projectData?.project?.id) {
      setError("Create a project first.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const task = await createTask(projectData.project.id, {
        mode: taskMode,
        chapter_count: chapterCount,
        start_chapter_index: 1,
      });
      const result = await runTask(projectData.project.id, task.id);
      const detail = await getTask(projectData.project.id, result.id);
      const refreshed = await getProject(projectData.project.id);
      setProjectData(refreshed);
      setTaskData(detail);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to run task");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm(chapterId: string) {
    if (!projectData?.project?.id) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const result = await confirmChapter(projectData.project.id, chapterId);
      const task = await getTask(projectData.project.id, result.id);
      const refreshed = await getProject(projectData.project.id);
      setProjectData(refreshed);
      setTaskData(task);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to confirm chapter");
    } finally {
      setLoading(false);
    }
  }

  async function handleParagraphAction(chapterId: string, action: "rewrite" | "expand", content: string) {
    if (!projectData?.project?.id) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const instruction = action === "rewrite" ? "Tighten the scene and sharpen the conflict." : "Add emotional reflection and sensory detail.";
      const result =
        action === "rewrite"
          ? await rewriteParagraph(projectData.project.id, chapterId, content, instruction)
          : await expandParagraph(projectData.project.id, chapterId, content, instruction);
      setRewriteResult(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Paragraph action failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="shell">
      <section className="panel">
        <h1>Novel Workshop MVP</h1>
        <p>Project creation, chapter generation, scoring loop, and admin-ready backend hooks.</p>
        <form onSubmit={handleCreateProject} className="form-grid">
          <label>
            Title
            <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
          </label>
          <label>
            Genre
            <input value={form.genre} onChange={(event) => setForm({ ...form, genre: event.target.value })} />
          </label>
          <label>
            Length Type
            <input value={form.length_type} onChange={(event) => setForm({ ...form, length_type: event.target.value })} />
          </label>
          <label>
            Template
            <select value={form.template_id} onChange={(event) => setForm({ ...form, template_id: event.target.value })}>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name} ({template.status})
                </option>
              ))}
            </select>
          </label>
          <label className="full">
            Outline Summary
            <textarea value={form.summary} onChange={(event) => setForm({ ...form, summary: event.target.value })} rows={4} />
          </label>
          <label>
            Character Cards
            <textarea value={form.character_cards} onChange={(event) => setForm({ ...form, character_cards: event.target.value })} rows={4} />
          </label>
          <label>
            World Rules
            <textarea value={form.world_rules} onChange={(event) => setForm({ ...form, world_rules: event.target.value })} rows={4} />
          </label>
          <label>
            Event Summary
            <textarea value={form.event_summary} onChange={(event) => setForm({ ...form, event_summary: event.target.value })} rows={4} />
          </label>
          <label>
            Default Mode
            <select value={form.mode_default} onChange={(event) => setForm({ ...form, mode_default: event.target.value as "manual" | "auto" })}>
              <option value="manual">manual</option>
              <option value="auto">auto</option>
            </select>
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Working..." : "Create Project"}
          </button>
        </form>
        {error ? <div className="error">{error}</div> : null}
      </section>

      <section className="panel">
        <h2>Task Control</h2>
        <div className="inline">
          <label>
            Mode
            <select value={taskMode} onChange={(event) => setTaskMode(event.target.value as "manual" | "auto")}>
              <option value="manual">manual</option>
              <option value="auto">auto</option>
            </select>
          </label>
          <label>
            Chapters
            <input type="number" min={1} max={10} value={chapterCount} onChange={(event) => setChapterCount(Number(event.target.value))} />
          </label>
          <button onClick={handleRunTask} disabled={loading || !projectData?.project?.id}>
            Run Task
          </button>
        </div>
        {projectData ? (
          <div className="status-grid">
            <div><strong>Project:</strong> {projectData.project.title}</div>
            <div><strong>Quota:</strong> free {projectData.quota.free_remaining} / monthly {projectData.quota.monthly_remaining}</div>
            <div><strong>Copyright:</strong> {projectData.copyright_notice}</div>
          </div>
        ) : null}
        {taskData ? (
          <div className="status-grid">
            <div><strong>Task Status:</strong> {taskData.task.status}</div>
            <div><strong>Mode:</strong> {taskData.task.mode}</div>
            <div><strong>Current Chapter:</strong> {taskData.task.current_chapter_index}</div>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <h2>Chapter Results</h2>
        {taskData?.chapters?.length ? (
          taskData.chapters.map((chapter: any) => {
            const selectedDraft = chapter.drafts.find((draft: any) => draft.selected);
            return (
              <article key={chapter.id} className="chapter-card">
                <header>
                  <h3>{chapter.title}</h3>
                  <span>{chapter.status}</span>
                </header>
                <p><strong>Rewrite Count:</strong> {chapter.rewrite_count}</p>
                <p><strong>Manual Review:</strong> {chapter.needs_manual_review ? "建议人工复核" : "not required"}</p>
                <div className="columns">
                  <div>
                    <h4>3 Outline Options</h4>
                    {chapter.outline_options.map((option: any) => (
                      <div key={option.id} className={option.selected ? "selected card" : "card"}>
                        <div><strong>Option {option.option_no}</strong> {option.selected ? "(selected)" : ""}</div>
                        <div>{option.content}</div>
                        <div>Conflict: {option.core_conflict}</div>
                        <div>Event: {option.key_event}</div>
                        <div>Hook: {option.ending_hook}</div>
                        <div>Scores: plot {option.score_plot}, consistency {option.score_consistency}, hook {option.score_hook}, final {option.final_score}</div>
                      </div>
                    ))}
                  </div>
                  <div>
                    <h4>Draft Versions</h4>
                    {chapter.drafts.map((draft: any) => (
                      <div key={draft.id} className={draft.selected ? "selected card" : "card"}>
                        <div><strong>Revision {draft.revision_no}</strong> {draft.selected ? "(final)" : ""}</div>
                        <div>{draft.content}</div>
                        <div>Reader score: {draft.final_score}</div>
                        <div>Issue: {draft.issue_summary}</div>
                      </div>
                    ))}
                  </div>
                </div>
                {selectedDraft ? (
                  <div className="final-box">
                    <h4>Final Chapter Text</h4>
                    <p>{selectedDraft.content}</p>
                    <div className="inline">
                      <button onClick={() => handleParagraphAction(chapter.id, "rewrite", selectedDraft.content)}>Rewrite Paragraph</button>
                      <button onClick={() => handleParagraphAction(chapter.id, "expand", selectedDraft.content)}>Expand Paragraph</button>
                      {taskData.task.status === "waiting_user_confirm" && !chapter.confirmed_by_user ? (
                        <button onClick={() => handleConfirm(chapter.id)}>Confirm Chapter</button>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })
        ) : (
          <p>No chapter results yet.</p>
        )}
      </section>

      {rewriteResult ? (
        <section className="panel">
          <h2>Paragraph Rewrite / Expand</h2>
          <p><strong>Consistency Note:</strong> {rewriteResult.consistency_note}</p>
          <div className="columns">
            <div className="card">
              <h4>Original</h4>
              <p>{rewriteResult.original}</p>
            </div>
            <div className="card">
              <h4>Updated</h4>
              <p>{rewriteResult.updated}</p>
            </div>
          </div>
          <div className="card">
            <h4>Diff</h4>
            {rewriteResult.diff.map((entry: any, index: number) => (
              <div key={`${entry.type}-${index}`} className={`diff-${entry.type}`}>
                {entry.type}: {entry.text}
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
