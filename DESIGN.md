---
name: 研岸 Ashore
description: 面向考研数学的安静学习工作台
colors:
  study-teal: "#13736f"
  study-teal-deep: "#0c5f5b"
  study-teal-soft: "#e3f1ed"
  study-teal-tint: "#f1f6f4"
  paper: "#ffffff"
  canvas: "#f7f9f8"
  ink: "#172429"
  body-ink: "#243536"
  secondary-ink: "#5b7073"
  muted-ink: "#667a7c"
  quiet-ink: "#899a99"
  border: "#e2eae7"
  border-strong: "#cbdad6"
  focus-ring: "#a9d7ca"
  warm-note: "#f6e8d5"
  warm-note-ink: "#925632"
  error: "#a6373d"
  error-soft: "#fdf2f1"
typography:
  display:
    fontFamily: "Segoe UI, Microsoft YaHei, sans-serif"
    fontSize: "29px"
    fontWeight: 680
    lineHeight: 1.25
    letterSpacing: "0"
  heading:
    fontFamily: "Segoe UI, Microsoft YaHei, sans-serif"
    fontSize: "20px"
    fontWeight: 680
    lineHeight: 1.3
    letterSpacing: "0"
  title:
    fontFamily: "Segoe UI, Microsoft YaHei, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "0"
  body:
    fontFamily: "Segoe UI, Microsoft YaHei, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.8
    letterSpacing: "0"
  label:
    fontFamily: "Segoe UI, Microsoft YaHei, sans-serif"
    fontSize: "12px"
    fontWeight: 650
    lineHeight: 1.5
    letterSpacing: "0"
rounded:
  xs: "4px"
  sm: "6px"
  md: "8px"
  round: "50%"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "36px"
components:
  button-primary:
    backgroundColor: "{colors.study-teal}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "11px 17px"
    height: "43px"
  button-primary-hover:
    backgroundColor: "{colors.study-teal-deep}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "11px 17px"
    height: "43px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.secondary-ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
    height: "40px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "40px"
  nav-item:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.secondary-ink}"
    rounded: "{rounded.sm}"
    padding: "0 13px"
    height: "42px"
  nav-item-selected:
    backgroundColor: "{colors.study-teal-soft}"
    textColor: "{colors.study-teal-deep}"
    rounded: "{rounded.sm}"
    padding: "0 13px"
    height: "42px"
  answer-source:
    backgroundColor: "{colors.study-teal-tint}"
    textColor: "{colors.secondary-ink}"
    rounded: "{rounded.sm}"
    padding: "13px 14px"
  record:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "16px 17px"
---

# Design System: 研岸 Ashore

## Overview

**Creative North Star: "The Quiet Study Desk"**

研岸的界面是一张安静的书桌，而不是一个热闹的聊天产品。它用白色纸张、低饱和青绿色和细线分隔，把注意力留给题目、公式与出处。信息密度中等，阅读留白充足；所有强调色都服务于当前动作，不做装饰。

这是一个 Operate 型界面：用户打开页面是为了提问、核对、练习和复盘。视觉系统应让状态清楚、动作可预期、长答案可读，避免把学习流程包装成营销页面或装饰性卡片集合。

**Key Characteristics:**

- 白纸与浅灰画布构成主要表面，青绿色只承担选中与主操作。
- 字体使用系统中文无衬线，依靠字号、字重和留白建立层级。
- 扁平优先，用 1px 细线、浅色底和间距表达分组，不依赖阴影。
- 6–8px 的小圆角保持精确感；圆形只用于头像等身份元素。
- 公式与长文需要可横向滚动的容器，移动端把操作放到底部拇指区。

## Colors

整体是冷白纸面上的低饱和青绿色系统，暖色只用于身份提示，红色只用于错误。

### Primary

- **Study Teal**: 主按钮、选中导航、焦点与关键链接。它出现得少，因此出现时具有明确行动含义。
- **Study Teal Deep**: 主按钮悬停与高强调文字，保持同一色相下更深的层次。
- **Study Teal Soft**: 选中导航、提示条与轻量反馈底色。
- **Study Teal Tint**: 引用原文抽屉、次级信息底色与轻量输入提示。

### Neutral

- **Paper**: 侧栏、输入框、记录与主要表面。
- **Canvas**: 应用背景与对话区外围。
- **Ink**: 标题与主要正文。
- **Body Ink**: 长回答与题干正文。
- **Secondary Ink / Muted Ink / Quiet Ink**: 元信息、辅助说明与空状态。小字号使用时必须检查对比度。
- **Border / Border Strong**: 分隔线、输入边界与轻微容器轮廓。
- **Focus Ring**: 键盘焦点外圈，不能只靠边框颜色变化表达焦点。

### Semantic

- **Warm Note**: 错因、类型标签与需要温和提醒的元信息。
- **Error**: 错误文字与错误按钮文字。
- **Error Soft**: 错误提示与错误结果的浅底。

### Named Rules

**The One Accent Rule.** 青绿色只出现在主操作、选中状态和关键状态上。页面大面积区域保持白色或浅灰。

**The No Decorative Color Rule.** 颜色必须说明状态或层级；不要用渐变、彩色光晕或装饰性色块填补空白。

## Typography

**Display Font:** Segoe UI with Microsoft YaHei fallback
**Body Font:** Segoe UI with Microsoft YaHei fallback
**Label Font:** same family, smaller and heavier

**Character:** 系统字体带来低摩擦的熟悉感，像一张干净的学习工作台。层级不靠花哨字体，而靠清晰的大小、字重和行距。

### Hierarchy

- **Display** (680, 29px, 1.25): 登录页主标题，只在空白的入口页面使用。
- **Headline** (680, 20px, 1.3): 页面标题与核心区块标题。
- **Title** (700, 18px, 1.1): 品牌名、空状态主标题与短标题。
- **Body** (400, 14px, 1.8): 回答、题干、解析与表单说明。长回答保持舒适行距。
- **Label** (650, 12px, 1.5): 元信息、知识点、来源与操作辅助文字。

### Named Rules

**The Readable Answer Rule.** 数学回答正文优先于界面装饰；不要为了“更像产品”压缩行距或缩短回答宽度。

## Layout

桌面端采用固定左侧栏与居中的 940px 工作区。侧栏宽 216px，页面左右内边距 36px；页头高度 95px，保持与内容区分离。聊天回答宽度限制在 720px，避免中文长段落失去阅读节奏。

练习、错题与规划页面共享同一个工作区宽度和 95px 页头。列表与结果使用开放的纵向流，不用多层卡片包裹。移动端在 680px 以下切换为底部五项导航；聊天和表单操作进入拇指区，页面内容改为单列。

## Elevation & Depth

系统默认是扁平的。层级由背景色、1px 边框和留白表达，不用宽大软阴影，也不叠加“边框 + 阴影”的幽灵卡片。结果面板和引用原文抽屉使用浅色底，而不是浮起阴影。

**The Flat-By-Default Rule.** 静止状态不出现阴影。需要强调时先增加底色或边框，再考虑动效。

## Shapes

圆角是克制的工具尺度：小控件与按钮使用 6px，较大的记录与结果面板使用 8px，标签使用 4px。头像使用圆形，除此之外不使用大圆角胶囊作为页面容器。

**The Small Radius Rule.** 圆角用于让控件显得可触，而不是让界面显得柔软；页面区块不包成圆角大卡片。

## Components

### Buttons

- **Shape:** 精确的小圆角（6px）。
- **Primary:** Study Teal 底、Paper 文字，最小高度 43px；用于提交、练习和生成等明确动作。
- **Hover / Focus:** 悬停加深为 Study Teal Deep；键盘焦点使用 2px Focus Ring 外圈。
- **Secondary:** Paper 底、Border Strong 边框、Secondary Ink 文字，最小高度 40px；用于刷新、清除与低风险动作。
- **Disabled:** 降低透明度并禁止指针，不能只靠颜色变化。

### Navigation

桌面侧栏使用白底、文字与图标并列的 42px 行。悬停使用 Study Teal Tint，选中使用 Study Teal Soft 与加粗青绿色文字。移动端变为底部五项导航，保留文字标签，不用纯图标导航。

### Inputs / Fields

输入框为 Paper 底、1px Border Strong、6px 圆角；聚焦时边框转青绿并显示 2px Focus Ring。文本域用于完整解题过程，最小高度 128px，允许垂直调整。错误提示靠近输入位置，使用 Error 文字与 Error Soft 底。

### Answer Sources

回答下方的出处区是一个开放的分隔块：顶部 1px 细线，标题显示“出处 · N 条”，明确引用的文件名与页码直接可见。用户点击“查看原文”后才展开 Study Teal Tint 底色中的片段抽屉，避免长回答一开始被来源信息压住。

### Records

错题与答题历史使用 Paper 底、1px Border、8px 圆角的重复记录。记录顶部显示知识点、错因与时间，题干使用 Body Ink；错因与订正放在原生 disclosure 中，保证键盘可操作。

### Segmented Control

题型筛选使用 Study Teal Tint 底的小型分段控件，选中项回到 Paper 底并加粗。它只用于少量互斥选项，不承担页面主操作。

## Do's and Don'ts

### Do:

- **Do** 用 Study Teal 标记主操作、选中状态和关键行动。
- **Do** 让长回答保持 720px 左右的可读宽度和 1.8 行距。
- **Do** 用边框、底色和留白表达层级。
- **Do** 在移动端把主操作放到拇指区，并保留导航文字。
- **Do** 让出处默认显示文件名与页码，原文按需展开。
- **Do** 为键盘焦点保留清晰的 2px 外圈。

### Don't:

- **Don't** 用大面积渐变、装饰性光晕或玻璃拟态。
- **Don't** 把页面区块做成层层嵌套的圆角卡片。
- **Don't** 用颜色作为唯一的状态表达。
- **Don't** 在回答正文里塞入开发者向的英文枚举或调试文案。
- **Don't** 把 36–40px 的图标按钮当作移动端主要触控目标。
- **Don't** 用装饰性图标替代清楚的文字操作。
