# LoadLab

WebSocket 长连接压测与容量拐点分析。

## 为什么单独做这个

HTTP 接口压测看的是 QPS 和响应时间；**长连接推送是另一回事**：

- 并发单位是「同时在线连接数」，不是「每秒请求数」；
- 服务端是主动下行，慢客户端会反过来拖累服务端；
- 真正的故障不是「请求失败」，而是「延迟慢慢升高，直到所有人都卡住」。

最常见的实现方式是广播循环里逐个 `await send()`。连接少的时候完全没问题，连接一多，一个客户端网络慢，整个广播循环就被它拖住，所有客户端的延迟一起上升 —— 这就是队头阻塞。这个问题用 HTTP 压测工具看不出来。

LoadLab 就是为这个场景写的：分级加压，测出推送延迟随并发变化的曲线，找到拐点，并对比两种服务端实现。

## 测什么

`target/push_server.py` 提供两个等价的推送服务，只有广播方式不同：

| 模式 | 广播实现 | 预期表现 |
|---|---|---|
| `naive` | 循环里 `await ws.send()`，串行发送 | 并发升高后延迟整体抬升（队头阻塞） |
| `optimized` | 每连接独立队列 + 独立发送协程，队列满则丢帧计数 | 慢客户端只影响自己，延迟稳定，代价是丢帧 |

两个模式的服务端逻辑、推送频率、报文大小完全一样，**唯一变量就是广播方式**，这样对比才有意义。

## 快速开始

```bash
pip install -e ".[dev]"

# 起目标服务
python target/push_server.py --port 8765 --mode naive --interval 0.1 --stats report/server-stats.jsonl

# 另开窗口：分级加压
loadlab run --target ws://127.0.0.1:8765 \
            --stages 10,50,100,200 \
            --duration 8 \
            --server-stats report/server-stats.jsonl \
            --out report/naive.json

# 生成图表和报告
loadlab report --inputs report/naive.json --labels naive --out report
```

对比两种实现：

```bash
loadlab report --inputs report/naive.json report/optimized.json \
               --labels naive optimized --out report
```

## 指标口径

| 指标 | 定义 |
|---|---|
| 延迟 | 客户端收到时刻 − 服务端写入报文的 `sentAt`（毫秒），**同机压测**时可用；跨机需要额外做时钟同步 |
| p50 / p95 / p99 | 对全部客户端的全部消息样本一起算，线性插值，与 Prometheus summary 口径一致 |
| 吞吐 | 所有客户端收到的消息总数 ÷ 本档实际耗时 |
| 错误率 | 连接失败 / 异常断开的客户端数 ÷ 并发数 |
| 丢帧 | 服务端统计的 `dropped` 增量（仅 optimized 模式会产生） |
| 事件循环延迟 | 服务端每秒采样一次，判断是不是被同步代码堵住了 |

## 拐点怎么判

只看「p95 超过 100ms」不行 —— 不同的机器基线差很远。判定规则是**相对自己**：

- p95 比上一档翻倍，且绝对值超过 50ms；或
- 开始出现连接错误 / 丢帧。

第一条命中即为拐点。拐点**前**那一档，就是当前配置下的安全并发。

## 产物

`loadlab report` 生成：

- `latency.png`：不同实现的 p95/p99 随并发变化
- `throughput.png`：吞吐随并发变化
- `report.md`：逐档表格 + 拐点结论 + 复现命令

## 结构

```
loadlab/
├─ loadlab/
│  ├─ client.py     # 单个压测客户端：连接、收推送、量延迟
│  ├─ runner.py     # 分级加压编排、服务端指标切片
│  ├─ stats.py      # 分位数、汇总、拐点判定
│  ├─ report.py     # 图表与 Markdown 报告
│  └─ cli.py        # 命令行
├─ target/
│  └─ push_server.py  # 被测服务（naive / optimized 两种广播）
└─ tests/             # 含真实起服务的集成测试
```

## 已知限制

- 压测客户端和服务端在**同一台机器**上，会互相抢 CPU；真正的容量评估应该分开机器，报告里给出的数字只能作相对比较；
- 延迟口径依赖两端时钟，同机没问题，跨机需要 NTP 或改用单向时延测量；
- 只压下行推送，没有覆盖上行订阅、鉴权、重连风暴等场景；
- `optimized` 模式的丢帧策略是「队列满即丢最旧/丢弃新帧」，生产环境更常见的是背压 + 降采样，这里只做演示。

## 参考

- 队头阻塞与背压的思路参考了 Kafka consumer / Netty 的 write buffer 设计文档；
- 分位数算法参考 Prometheus summary 的线性插值口径；
- 代码为自行实现，未引用上述项目源码。

## License

MIT
