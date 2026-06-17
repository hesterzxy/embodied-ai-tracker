# Vibe Coding 进化 · 具身智能网页

---

## 2026-06-13 复盘 4

### 三十分钟复盘

| 维度 | 内容 |
|---|---|
| **卡点日志** | **卡点1：来源编号 Unicode 上限**<br>圈数字符①-⑳只能到 20，超过后自动变成括号格式⑴⑵...，导致网页上编号格式混乱。用户发现后要求统一格式。<br>绕过去：改成纯数字 [1] [2] [3] 格式，无上限。耗时约 3 分钟。<br><br>**卡点2：GitHub Workflow 报错 — `cache: 'pip'` 找不到 requirements.txt**<br>`actions/setup-python@v5` 的 `cache: 'pip'` 配置会自动查找 requirements.txt，项目中没有这个文件就报错，导致 workflow 标红失败。<br>绕过去：创建 `requirements.txt`，写上 `anthropic>=0.30` 和 `openai>=1.0`，既修复报错又为后续依赖管理铺路。耗时约 2 分钟。<br><br>**卡点3：GitHub 安全策略禁止命令行改 `.github/workflows/`**<br>用 PAT push workflow 文件时被拒绝——"refusing to allow a Personal Access Token to create or update workflow .github/workflows/... without workflow scope"。<br>绕过去：不在命令行改 workflow，而是创建 requirements.txt 让现有配置生效；workflow 本身的改动需要用户在网页上做。耗时约 3 分钟理解并找到替代方案。<br><br>**卡点4：fetch_news.py 时区 bug**<br>`datetime.now() - pub_date` 时报 `TypeError: can't subtract offset-naive and offset-aware datetimes`——RSS 源返回的日期有时带时区有时不带。<br>绕过去：在 `normalize_date` 函数中强制为所有日期添加 UTC 时区，统一时间比较逻辑。耗时约 5 分钟调试 + 修复。<br><br>**卡点5：news.json 冲突导致 rebase 失败**<br>在做 Make box 新格式的大改动时，远程 fetch-news workflow 自动跑了一次，push 了新的 news.json。本地 rebase 时两边 news.json 内容不同 → 冲突。<br>绕过去：git reset --hard origin/main 回到最新，然后重新做改动。教训：大改动前先 pull 一次；news.json 这种频繁变动的文件用 `checkout --theirs` 快速合并。耗时约 5 分钟。 |
| **能力边界** | **惊艳（0 到 1）**<br>- 用一套 Python 脚本 + GitHub Actions 实现了"从 RSS 抓取新闻 → 分类 → 自动 commit push"的完整链路，从无到有搭建了一个真正有生产感的小系统。<br>- JavaScript 渲染逻辑写得有章法：从 summary 提取、日期判断、高亮逻辑、localStorage 状态管理，一气呵成。<br>- 能理解用户"这两个圈数字不一样"的非技术描述，定位到 Unicode 字符范围问题。<br><br>**拉胯（1 到 10，调试、记不住上下文）**<br>- Git rebase 冲突处理不熟练，reset 后需要重做所有改动，浪费时间。如果更有条理地用分支管理（先在 feature 分支做，review 完再 merge），就不会丢代码。<br>- 忘记了之前 session 中已经改好的 categorize 函数内容（在新分类和旧分类之间混淆），需要反复查证文件当前状态。<br>- "一周以内信息淡蓝色高亮"这个功能，依赖 sources 字段中的日期名提取，但 date 格式不统一，这个判断逻辑很脆弱——没有做容错处理。 |
| **信任缺口** | 让我不确定的几个时刻：<br>1. **workflow 报错的根本原因**——最初怀疑是 actions/checkout@v4 版本问题，后来才看清是 `cache: 'pip'` 找不到文件。需要反复读 error log 才确认。<br>2. **LLM 三角验证真的能用吗**——`auto_update.py` 需要 API Key，即使 workflow 跑起来了，也不知道 Claude 能否理解我们要的"对比表数据"的格式。这部分还没有真实运行验证。<br>3. **news.json 的新分类会不会覆盖旧新闻**——重新跑 `categorize` 时担心是否会破坏已有数据结构。验证方式：在本地用 Python 脚本跑了一次 `print` 检查前 10 条，字段都对。 |
| **人机分工** | **Agent 做的**<br>- 写所有代码：fetch_news.py 爬虫 + 分类、auto_update.py LLM 验证脚本、index.html 的渲染逻辑和样式、requirements.txt、workflow 文件<br>- 诊断技术 bug：时区 TypeError、cache 找不到文件、GitHub 安全策略、Git 冲突<br>- Git 操作：commit、push、pull、rebase 回退<br>- 整体产品结构判断：对比表 + 赛道动态 + 每周汇总的三段式设计<br><br>**我亲自做的（不可替代的判断）**<br>- 定义"分类方向"——技术突破/产品量产/商业订单/资本动态，这是战略判断，不是代码能决定的<br>- 决定 Make box 的视觉格式——10字内 summary + 冒号 + bullet，这个设计品味是人的判断<br>- 决定一周内信息用淡蓝色、而不是红色/绿色——这是设计敏感度<br>- 决定"不要报错退出"而要"优雅退出"，这是对产品容错性的判断 |
| **工具差异** | 这段主要用 Trae，没有对比 Cursor/Claude Code。但有几点感受：<br>- **Trae 的 Skill 系统有潜力**：Vibe Coding Evolution 这种"每30分钟强制复盘"的 discipline，如果真的坚持下来，对面试准备很有价值。但需要用户主动调用，容易忘记。<br>- **多轮对话上下文记忆**：从 session summary 恢复后，对之前做过什么（"之前改好了 categorize，但 reset 后丢了"）的记忆不完整，需要用户反复提醒。<br>- **文件读取 / 编辑速度**：Read → Edit → Write 的链路顺畅，比手动打开编辑器快多了。 |
| **情绪** | **想摔电脑**：<br>1. Git rebase 冲突时——本地做了一大段改动（Make box、公司增删、淡蓝高亮），结果一个 rebase 失败全丢。那一刻真的有点烦。<br>2. GitHub workflow 反复报各种莫名其妙的错——Node.js deprecation、cache 找不到文件、API key 缺失——一个接着一个，像打地鼠。<br><br>**爽**：<br>1. 看到 news.json 第一次成功抓到"宁王系，排队 IPO"这条新闻，确认整个链路跑通了的时候，有成就感。<br>2. Make box 新格式的设计决策——从用户说"总结一下，然后冒号，然后 bullet"到真的实现出来，这个从概念到代码的转化过程很爽。<br>3. "一周内信息淡蓝色高亮"这个功能，是很好的信息设计——不是谁都会想到做数据新鲜度可视化的。<br>4. 复盘本身就是一种爽——停下来整理今天踩过的坑，写清楚，明天继续时就不会再踩同一个了。 |

---

### 今日知识积累

| 概念 | 一句话概括 |
|---|---|
| **Unicode 圈数字符上限** | ①-⑳ 只到 20，超过后字符集变，用纯数字编号 [1] [2] 更稳妥 |
| **GitHub Actions `cache: 'pip'` 机制** | setup-python 的 cache 配置会自动查找 requirements.txt / pyproject.toml，没有就报错 |
| **GitHub Workflow 文件安全策略** | PAT 默认没有 `workflow` scope，不能通过命令行修改 `.github/workflows/` 下的文件，需在网页上编辑 |
| **offset-naive vs offset-aware datetime** | Python datetime 分"无时区"和"有时区"两类，不能直接相减，需要统一时区后再比较 |
| **Git rebase 失败不丢代码的正确姿势** | `git rebase --abort` → `git reset --hard origin/main` → 重新做改动；或用分支隔离后再 merge |
| **RSS 爬虫的常见故障模式** | SSL 证书校验失败、HTTP 500、目标站点禁 UA——每个 RSS 源独立 try/except 捕获，单个失败不影响整体 |
| **具身智能赛道的信号分类法** | 按战略价值而非行业分类：技术突破（底层能力）/ 产品量产（从实验室到交付）/ 商业订单（真实需求信号）/ 资本动态（融资、IPO、并购） |
