export type Mode = "manual" | "auto";

export type ProjectForm = {
  title: string;
  genre: string;
  genres: string[];
  length_type: string;
  template_id: string;
  summary: string;
  character_cards: string;
  world_rules: string;
  event_summary: string;
  story_beats: string;
  mode_default: Mode;
};

export const initialForm: ProjectForm = {
  title: "",
  genre: "fantasy",
  genres: ["fantasy"],
  length_type: "long",
  template_id: "",
  summary: "",
  character_cards: "",
  world_rules: "",
  event_summary: "",
  story_beats: "",
  mode_default: "manual",
};

export const labels = {
  appTitle: "智能小说协同生成平台",
  appSubtitle: "支持项目创建、章节续写、评分回流，以及面向运营后台的基础能力。",
  sections: {
    projectSetup: "项目创建",
    taskControl: "任务控制",
    chapterResults: "章节结果",
    templateManager: "模板管理",
    adminPanel: "后台联动",
  },
  fields: {
    title: "项目标题",
    genre: "小说题材",
    lengthType: "篇幅类型",
    template: "选用模板",
    summary: "总纲摘要",
    characterCards: "角色卡",
    worldRules: "世界观规则",
    eventSummary: "事件摘要",
    outlineTemplate: "大纲模板",
    storyBeats: "阶段节拍",
    defaultMode: "默认模式",
    runMode: "生成模式",
    chapterCount: "续写章节数",
    templateName: "模板名称",
    styleRules: "文风规则",
    worldTemplate: "世界模板",
    characterTemplate: "角色模板",
    freeDelta: "赠送免费章节调整",
    monthlyDelta: "当月剩余调整",
    planDailyQuota: "日免费章节",
    planMonthlyQuota: "月免费章节",
    dailyDelta: "当日剩余调整",
    bonusDelta: "赠送免费章节调整",
    blockedTerms: "屏蔽词",
    copyrightNotice: "版权提示文案",
    planName: "套餐名称",
    freeQuota: "日免费章节",
    monthlyQuota: "月免费章节",
    planDescription: "套餐说明",
    orderAmount: "订单金额",
    orderStatus: "订单状态",
    orderNote: "订单备注",
  },
  actions: {
    createProject: "创建项目",
    generateFoundation: "AI 生成基础设定",
    runTask: "开始续写",
    confirmChapter: "确认本章",
    regenerateOutlines: "重新生成走向",
    selectOutline: "选用该走向",
    saveOutline: "保存走向并重生成正文",
    regenerateDraft: "重新生成正文",
    saveDraft: "保存正文修改",
    createTemplate: "创建模板",
    saveTemplate: "保存模板",
    publishTemplate: "发布模板",
    refreshAdmin: "刷新后台数据",
    adjustQuota: "调整额度",
    saveSafety: "保存安全策略",
    createPlan: "新建套餐",
    savePlan: "保存套餐",
    editPlan: "编辑套餐",
    activatePlan: "设为默认套餐",
    createOrder: "新增订单",
    saveOrder: "保存订单",
  },
  states: {
    working: "处理中...",
    noChapterResults: "当前还没有章节结果。",
    noProject: "请先创建项目。",
  },
  info: {
    project: "项目：",
    quota: "剩余额度：",
    copyright: "版权提示：",
    taskStatus: "任务状态：",
    currentMode: "当前模式：",
    currentChapter: "当前章节：",
    rewriteCount: "回流重写次数：",
    manualReview: "人工复核：",
    options: "3 个剧情走向方案",
    drafts: "正文版本",
    finalText: "最终章节正文",
    editableHint: "未确认前可修改走向与正文",
    contentGoal: "正文目标长度：约 3000 中文字符",
    plans: "套餐信息",
    orders: "订单记录",
    activePlan: "默认套餐",
    safety: "安全策略",
    logs: "任务日志",
    logAction: "事件",
    logTime: "时间",
  },
  errors: {
    createProject: "创建项目失败",
    runTask: "执行任务失败",
    confirmChapter: "确认章节失败",
    outlineAction: "走向操作失败",
    draftAction: "正文操作失败",
    templateAction: "模板操作失败",
    adminAction: "后台操作失败",
  },
  review: {
    required: "建议人工复核",
    notRequired: "当前不需要",
  },
  selection: {
    selected: "（已选中）",
    final: "（最终保留）",
  },
  templateStatus: {
    published: "已发布",
    draft: "草稿",
  },
};

export const modeLabels: Record<Mode, string> = {
  manual: "人工确认",
  auto: "自动生成",
};

export const genreLabels: Record<string, string> = {
  romance: "言情",
  fantasy: "玄幻",
  horror: "恐怖",
  wuxia: "武侠",
  xianxia: "仙侠",
  sci_fi: "科幻",
  suspense: "悬疑",
  historical: "历史",
  urban: "都市",
  mystery: "推理",
  thriller: "惊悚",
  detective: "侦探",
  military: "军事",
  game: "游戏",
  esports: "电竞",
  workplace: "职场",
  campus: "校园",
  youth: "青春",
  family: "家庭",
  adventure: "冒险",
  action: "动作",
  martial_arts: "热血",
  post_apocalypse: "末世",
  cyberpunk: "赛博朋克",
  steampunk: "蒸汽朋克",
  space_opera: "太空歌剧",
  dystopian: "反乌托邦",
  time_travel: "穿越",
  rebirth: "重生",
  alternate_history: "架空历史",
  palace_intrigue: "宫斗",
  court_politics: "权谋",
  cultivation: "修真",
  monster_taming: "御兽",
  livestream: "直播",
  fanfiction: "同人",
  slice_of_life: "日常",
};

export const lengthLabels: Record<string, string> = {
  long: "长篇",
  short: "短篇",
};

export const statusLabels: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  waiting_user_confirm: "等待人工确认",
  completed: "已完成",
  failed: "失败",
  pending: "待处理",
  outlining: "生成剧情走向中",
  outline_selected: "已选定剧情方案",
  drafting: "生成正文中",
  reviewing: "评分审核中",
  revising: "回流重写中",
  needs_manual_review: "建议人工复核",
  confirmed: "已确认",
};

export const diffTypeLabels: Record<string, string> = {
  unchanged: "未变更",
  removed: "删除",
  added: "新增",
};

export function translateLabel(value: string, mapping: Record<string, string>): string {
  return mapping[value] ?? value;
}

export function templateStatusLabel(status: string): string {
  if (status === "published") {
    return labels.templateStatus.published;
  }
  if (status === "draft") {
    return labels.templateStatus.draft;
  }
  return status;
}
