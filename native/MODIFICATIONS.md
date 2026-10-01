# GhostLock 诊断修改

基础项目：YuKongA/ghostlock-app，提交 `b28529cb31ef6cfe597bb8994eec411ef87513ea`，Apache-2.0。原许可保留在 native/LICENSE。

诊断修改日期：2026-09-29；本次公开整理为修改文件补充显著的说明和日期，2026-10-01。

修改主要记录线程身份、阶段状态、实际退出与 join 结果，补充诊断辅助文件。日志会改变时序，不能把诊断程序的一次成功解释为稳定性修复。未宣称发明上游提权方法。

编译步骤见 docs/build.md 和 scripts/build_native.py。修改的源码与固定上游的差异文件如下：

- `src/core/attack/ops.hpp`
- `src/core/main.cpp`
- `src/core/race/diagnostics.hpp`
- `src/core/race/pi_race.cpp`
- `src/core/race/threads.cpp`
- `src/core/route/tcp_zerocopy_route.cpp`
- `src/core/tests/number_parse_test.cpp`
- `src/core/tests/runtime_paths_test.cpp`
