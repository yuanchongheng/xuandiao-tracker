# 选调雷达 · 2027届

这是一个静态站点 + GitHub Actions 公告监测器，用于汇总全国 31 个省级地区的 2027 届选调信息。网站展示正式公告、报名起止、分岗位截止、笔试安排、省份进度、日历和收藏；自动监测负责发现新线索并刷新监测状态。

## 来源与发布规则

来源按三级处理：

1. **政府官网优先**：党委组织部门、政府、人社、人事考试机构等 `*.gov.cn` 原始公告。新发现的政府链接先进入 `review_queue.json`，人工核对正文、附件和适用范围后再写入正式数据。
2. **吉林大学就业网**：仅接受 `jdjywpt.jlu.edu.cn` 和 `jdjyw.jlu.edu.cn`。吉林大学就业网发布的 2027 届选调通知按本站规则可自动进入正式 `data.json`，无需人工二次核验；程序只结构化正文中明确出现的报名/考试日期，不猜测未公布时刻、资格或岗位条件。
3. **其他高校官方就业网**：只接受 `source_policy.py` 白名单中的高校域名，存入 `third_sources.json` 作为独立补充参考，不自动进入正式数据和日历。

监测失败不等于“没有公告”。网站始终以公告原文、附件、岗位表和后续更正为最终依据；同一省份如果按高校、岗位、批次分别发布，必须分别理解适用范围和截止时间。

## 数据文件

- `data.json`：正式发布数据，首页、卡片、省份进度和日历都以它为准。
- `review_queue.json`：仍需人工处理的政府来源候选；吉林大学候选在自动发布后会变为 `auto_published` / `auto_covered`。
- `third_sources.json`：其他高校官方就业网补充线索，仅供交叉查找。
- `watch_state.json`：文章、目录、搜索去重状态。
- `monitor_status.json`：最近一次监测成功数、备用源、错误和自动发布状态。
- `sources.json`：直连来源、31 地区搜索和第三来源批次配置。
- `source_policy.py`：来源域名分级白名单。

`build.py` 负责正式数据结构、来源、日期关系和 HTML 内嵌快照校验；`validate_extra.py` 检查跨文件不变量；`tests/` 保存离线回归测试。

## 时间字段约定

时间戳统一使用带 `+08:00` 时区的 ISO 8601。若公告只公布“某日开始”而没有开放时刻，数据使用该日 `00:00:00+08:00` 作为日期哨兵，同时设置 `startDateOnly: true`；前端只显示日期，并从该日开始按“已开放”处理，不显示“时刻待核实”。程序禁止继续使用旧字段 `startTimeUnknown`。

同一公告存在不同岗位/层级截止时，使用 `deadlines` 单独记录，不能把最晚截止时间显示成所有岗位统一截止。

## 自动监测与部署

工作流位于 `.github/workflows/site.yml`。计划任务每 3 小时一次，北京时间约为：

`02:17 / 05:17 / 08:17 / 11:17 / 14:17 / 17:17 / 20:17 / 23:17`

GitHub Actions 的 `schedule` 不保证严格准点。人工 push 或 `workflow_dispatch` 也会运行完整检测；由监测机器人写回数据产生的 push 会跳过第二次完整 workflow，避免重复扫描和重复部署。

每轮主要流程：

1. 清理和校验现有正式数据；
2. 检查已配置的政府/JLU 直连文章和索引；
3. 对 31 个地区运行政府/JLU 搜索发现；
4. 轮换第三来源高校搜索，并逐轮检查配置的高校目录；
5. 自动发布 JLU 候选、补充明确时间、规范省份和已知数据；
6. 重新生成 `index.html` 离线快照；
7. 运行结构校验和回归测试；
8. 如数据发生变化则由机器人提交，并部署 GitHub Pages。

第三来源目前按 4 个批次轮换，每 3 小时检查一个批次，约 12 小时覆盖一轮配置的高校搜索批次；独立配置的高校目录每轮尝试检查。第三来源永远不因“搜索到了链接”而自动成为正式公告。

## 本地检查

```bash
python -m pip install -r requirements.txt
python data_hygiene.py
python build.py
python build.py --check
python validate_extra.py
python -m unittest discover -s tests -v
```

联网监测：

```bash
python monitor.py
python monitor.py --skip-discovery
```

`monitor.py` 不直接编辑 `data.json`；正式自动发布由随后执行的 `jlu_auto_publish.py` / `jlu_timing_fix.py` 等步骤完成。程序只请求公开 HTTPS 页面，不绕过登录、验证码或访问限制。抓取失败会记录到 `monitor_status.json`，不会被解释成“当地没有公告”。

## GitHub Pages

1. 将项目放在仓库 `main` 分支，保留 `.github/`。
2. 在 `Settings → Pages → Build and deployment → Source` 选择 **GitHub Actions**。
3. 确保 Actions 具备仓库内容写权限；如需新线索 Issue 提醒，需启用 Issues。
4. 可在 `Actions → Monitor announcements and publish site → Run workflow` 手动运行一次。

页面从 `data.json` 和内嵌快照加载正式数据；用户浏览器本地收藏/进度不会反向写入仓库。
