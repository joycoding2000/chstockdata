# Owner Acceptance 区间缺陷重做 r1 交接

- 阶段/步骤：R2.1 Owner Acceptance 缺陷最小修复及有限离线验证。
- 原仓库 HEAD：`42bd44ef4d695aa3e88cfab4ebc3417660d0437a`；新快照无 `.git`、未提交，恰好修改 3 个文件。
- 根因：`effective_end=None` 无限期适用，忽略受控缓存中认证的复牌日期。
- 修复：只有受控 packaged 对象身份获得日期适用资格；复牌日未知 clock 保守 UNKNOWN，之后仅撤销对应旧 halt。caller/current 任意 date、SHA 或 verified 标记不能解除阻断。
- 原始事实：保留 start、end=None、源 SHA、完整 raw fields/provenance；过期或已解析事件仍出现在 official_events。
- 证据：旧 wheel 原样独立离线注入复现 exit 0；RED 13 failed/9 passed；GREEN 22 passed；指定四文件 150 passed（原128+新增22）；RH1 静态 exit 0，24路径、真实 baseline 新增行通过，287项历史债务继续可见。
- verdict：有限实现验证 PASS；新统一 Gate 尚未运行，整体 Gate 为 INSUFFICIENT_EVIDENCE，未宣称 Owner 接受。
- 阻塞/范围：无实现阻塞，无范围扩张；未改旧源码、旧 wheel、旧证据、SIOS，未 build/commit/push/tag/publish/推进阶段。
- 下一步：root 独立有限验证，fresh spec→quality 审核后再按授权处理新 wheel 与统一 Gate；不代表下一阶段已获授权。

完整命令、exit/log/JUnit/hash 见各 `.command.json` 和 `implementation-summary.json`；全量三文件 diff 见 `source-relative-old-rework.patch`。所有新增日期运输数据均是确定性注入，不是新 live 资格证据。
