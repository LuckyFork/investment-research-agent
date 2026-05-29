# Replay / Eval Benchmark Cases

`cases.json` 用于第一版 `Replay / Eval Harness` 的固定题集输入。

每条 case 当前支持：

- `id`
- `query`
- `expected_complexity`
- `expected_route`
- `expected_documents`
- `expected_pages`
- `must_include_terms`
- `should_pass_compliance`

建议后续把 `expected_documents / expected_pages` 绑定到真实 demo 文档上，这样评测结果会更接近面试场景。
