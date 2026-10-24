# chstockdata 历史资产有界清理收口

日期：2026-10-24
Owner 裁决：RESEARCH_ASSET_REVIEW=PASS；RESEARCH_INDEX=PASS；DECISION_QUEUE=PASS；RETENTION_PLAN=PASS_WITH_EXCLUSIONS。清理授权为 A、B、C1、D；C2 defer；MAIN_CHANGE=NO；NEW_RESEARCH_AUTHORIZATION=NO。

执行依据为研究整理提交 ad6e871d415b87c7fcb8fd697c1a6d7107b05363 及其分类、集合校验、备份覆盖和 Git 引用记录。本记录只覆盖 chstockdata。

## 实际清理

- A：删除 27,584 个文件，逻辑字节 640,955,907。包括五个历史安装环境（core、gate、W0 dev、v0.4.1 sdist-env、wheel-env）、13 个 Ruff 缓存文件、清单中 5 个标准 pytest 缓存文件，以及精确列出的 336 个 .pyc。所有目录目标在执行前与清单的文件数/字节数一致，无嵌套 Git 仓库、重解析点或进程占用；选择文件逐项匹配且删除成功。
- B1：删除两份重复冻结 var，共 12,014 个文件、629,207,252 字节。两份候选各 6,007 文件，逐文件路径、长度和 SHA-256 均与保留原件相同。先在 Owner 指定的 E: My Passport 建立独立副本并完成逐文件验证，再执行删除。保留副本为 E:\Backup\chstockdata\research-assets\2026-10-24\v042-frozen-var；清单为同目录 MANIFEST-v042-frozen-var.json，SHA-256 为 9a2805f6611ec3f66fc19ec9820001b5ed500db46ca750167f5013b5111fcf60，集合身份摘要为 3ef6b0496a4e56b3b71ac9a18ed17746fcfdd47d6d1c30b6739841049c54dec3。保留的 D: 原件 build/v042-qualification/sios/var 仍有 6,007 个文件、314,603,626 字节。
- B2：删除三份已核验等价的消费者源副本，共 750 个文件、8,399,304 字节。owner-acceptance-rework-r1 中的三份原件仍在；copy-attempt 父目录未删除，其余 88 个顶层项完整保留。
- C1：非强制 git worktree remove 成功移除 C:\Users\Administrator\.codex\worktrees\v042-controlled-release\chstockdata。移除前 HEAD 为 a34c8c25b78a4b3a9f2263a69e54977a618cfbbd，跟踪状态干净，10 个 ignored 项共 37,172 字节且均为已确认的 Ruff/egg-info 生成物；该 HEAD 仍由本地和远端 codex/v042-release-audit 引用。逻辑清理统计为 431 个文件、6,356,663 字节（按既有口径排除 64 字节 Git worktree 指针）。未使用强制移除。
- D：删除 7 个本地候选分支引用和 8 个 GitHub 远端分支引用。逐项复核了原审查 SHA、实时远端 SHA、无开放 PR、无活动 worktree 使用及保留引用可达性；远端删除后逐项确认引用消失。每个远端删除使用精确 expected-SHA lease，不推送提交、不改写提交历史。

## 分支恢复 crosswalk

所有表中提交仍可通过未变更的本地 main（a2072d0c722d7f7935309a15cef945bc8ecbef08）定位；表中附加锚点也已复核存在。删除的远端引用已由 GitHub 实时查询确认缺失。

| 删除的分支名 | 删除前 head SHA（本地 / 远端） | 保留恢复锚 |
|---|---|---|
| codex/cached-ohlcv-compatibility-hardening | 4c7f90e317ad5a12bc30b5a1ab29b3b60eee9efd / 4c7f90e317ad5a12bc30b5a1ab29b3b60eee9efd | main；SSD migration 备份分支 |
| codex/phase41-routing-observation | a67f271af805b1de18069eb2fa3f6f0bc67b4906 / 同左 | main；SSD migration 备份分支 |
| codex/rh3-b4-live-qualification-evidence | e62cbfa56032de7ed454260cc3dfe34aed8e0161 / 同左 | main；DR03 与 SSD migration 备份分支 |
| codex/rh3-b5-candidate-freeze-preflight | 42bd44ef4d695aa3e88cfab4ebc3417660d0437a / 88f9b6677ade4a6ed280c865e6cf1edaf625a49f | main；C2 仍 detached 于 42bd44e；codex/ssd-migration-rh3b5-worktree-2026-10-23；v0.4.1 tag |
| codex/trading-calendar-structured | b78477f8e6984b374d3c64b45cf550a2c77ea6eb / 同左 | main；SSD migration 备份分支 |
| codex/v042-controlled-release | 17af23fe8183f740150dc01dd877473afe3911b7 / 同左 | main；v0.4.2 tag；codex/v042-release-audit |
| docs/v0.4.2-post-release-closeout | 0dc85e3e43588c5781771486a3c6f80c4be7714f / 同左 | main；v0.4.3 tag |
| docs/v0.4.0-retrospective-design-audit | c6f03252645a817099d4d6856e98a48e5008a0f7（仅远端） | main；v0.4.0 tag |

## 保留范围与验收

本地 main 仍为 a2072d0c722d7f7935309a15cef945bc8ecbef08，GitHub main 仍为 5584f5fcacccef9a9531a7a32b8463ea6771d312；tracked 工作区和索引干净，本轮未改动或推送 main。三个 SSD migration 备份分支、DR03 分支、codex/v042-release-audit、研究整理分支以及 v0.1.0、v0.2.0、v0.4.0 至 v0.4.3 tags 均仍在本地和远端，SHA 未变。

DR03 worktree（88e0ac6）、W0 worktree 与本地候选工件（69957a5）、C2 v042-opening-cr worktree（42bd44e）均仍存在且 HEAD 不变。H01、H04、DR03 证据、.rh3a2-vipdoc 唯一来源版本、研究索引和决策队列仍可访问。根 .pytest_cache 中 1,392 个非标准调查/证据文件保留；其余未列入精确授权集合的研究文件未清理。未运行全量 pytest、资格验证、发布 Gate 或 Git GC/prune。

逻辑删除共 40,779 个文件、1,284,919,126 字节（按原盘点口径排除 Git 元数据）。磁盘空闲空间按清理时前后读数记录：D: 25,696,501,760 → 27,052,453,888（+1,355,952,128）；C1 移除前后 C: 295,082,758,144 → 295,089,913,856（+7,155,712）；E: 备份前后 351,233,310,720 → 350,903,635,968（−329,674,752）。这些是各卷的实际空闲字节变化；D:/C: 与 E: 数值分别反映清理和新增备份的影响。

PROJECT=chstockdata
RESEARCH_ASSET_OWNER_ACCEPTANCE=PASS
RETENTION_PLAN_ACCEPTANCE=PASS_WITH_EXCLUSIONS
CLEANUP_AUTHORIZATION=YES_BOUNDED
FROZEN_VAR_RETAINED=YES
E_DRIVE_BACKUP=VERIFIED
H01_H04_DR03_EVIDENCE=PRESERVED
W0_ARTIFACTS=PRESERVED
DR03_WORKTREE=PRESERVED
C2_WORKTREE=PRESERVED
MAIN_UNCHANGED=YES
SSD_BACKUP_BRANCHES=PRESERVED
CLEANUP_CLOSEOUT=CLOSED

H04 消费者 Acceptance、DR03 重新资格、S07/W5-H 具名缺证仍按原有决策状态处理；本次没有启动这些研究工作。