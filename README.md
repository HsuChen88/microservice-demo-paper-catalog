# Paper Catalog Service — 技術文件

## 目錄

- [服務概述](#服務概述)
- [為什麼實作此微服務](#為什麼實作此微服務)
- [架構設計](#架構設計)
- [目錄結構](#目錄結構)
- [各模組詳細說明](#各模組詳細說明)
- [API 規格](#api-規格)
- [資料模型](#資料模型)
- [Kafka 事件消費機制](#kafka-事件消費機制)
- [Circuit Breaker 容錯機制](#circuit-breaker-容錯機制)
- [Prometheus 監控指標](#prometheus-監控指標)
- [組態設定](#組態設定)
- [存取方式](#存取方式)
- [效能分析](#效能分析)
- [建置與部署](#建置與部署)
- [CI/CD Pipeline](#cicd-pipeline)

---

## 服務概述

**Paper Catalog Service** 是論文館藏微服務架構中的索引查詢服務，負責接收來自 Submission Service 的論文建立事件，建立館藏索引，並提供快速查詢介面。採用 Python 3.11 + FastAPI 非同步框架建構，搭配 asyncpg 與 aiokafka 實現全非同步 I/O。

| 屬性 | 值 |
|---|---|
| 框架 | FastAPI |
| 語言 | Python 3.11 |
| 資料庫 | PostgreSQL（asyncpg） |
| 訊息佇列 | Apache Kafka（aiokafka） |
| HTTP Client | httpx（非同步） |
| 容錯機制 | 自製 async Circuit Breaker |
| 監控指標 | prometheus_client |
| 套件管理 | uv |
| 服務埠號 | 8082 |

---

## 為什麼實作此微服務

1. **讀寫分離（CQRS 精神）**：Submission Service 負責論文的「寫入」，Catalog Service 負責館藏的「查詢」。兩者的存取模式、流量特性與擴展需求截然不同，獨立服務可各自優化。

2. **事件驅動的最終一致性**：透過訂閱 Kafka topic `paper-events`，Catalog Service 在 Submission Service 建立論文後自動同步資料，無需同步 API 呼叫，降低服務間耦合。

3. **異質技術棧展示**：故意採用 Python（FastAPI）而非 Java（Spring Boot），展示微服務架構中不同服務可使用最適合的技術棧，透過 Kafka 協定與 REST API 實現跨語言通訊。

4. **獨立擴展與部署**：查詢流量通常遠大於寫入流量，Catalog Service 可獨立擴展至更多副本而不影響 Submission Service。

5. **容錯降級**：當 Submission Service 不可用時，透過 Circuit Breaker 保護，避免連鎖故障（cascading failure），Catalog Service 仍可從本地資料庫提供查詢服務。

---

## 架構設計

```
                    ┌──────────────────┐
                    │ Submission Svc   │
                    │ (Java/Spring)    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   Kafka Topic    │
                    │  "paper-events"  │
                    └────────┬─────────┘
                             │
┌────────────────────────────┼─────────────────────────────────┐
│           Paper Catalog Service (Python/FastAPI)             │
│                            │                                 │
│                   ┌────────▼──────────┐                      │
│                   │  Kafka Consumer   │                      │
│                   │  (aiokafka)       │                      │
│                   └────────┬──────────┘                      │
│                            │ upsert                          │
│                            ▼                                 │
│  ┌─────────────┐    ┌────────────┐    ┌──────────────────┐  │
│  │  FastAPI     │───▶│ PostgreSQL │    │ Submission Client│  │
│  │  REST API    │    │ (asyncpg)  │    │ (httpx + CB)     │  │
│  └──────┬──────┘    └────────────┘    └──────────────────┘  │
│         │                                                    │
│         ├── GET /api/v1/catalog                              │
│         ├── GET /api/v1/catalog/{id}                         │
│         ├── GET /health                                      │
│         └── GET /metrics                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**核心元件關係**：

| 元件 | 職責 | 對應模組 |
|---|---|---|
| FastAPI App | HTTP 路由、中介層、生命週期管理 | `main.py` |
| Kafka Consumer | 訂閱 `paper-events`，消費事件寫入 DB | `kafka_consumer.py` |
| Submission Client | 透過 HTTP 呼叫 Submission Service（含 Circuit Breaker） | `submission_client.py` |
| Circuit Breaker | 非同步斷路器，保護外部 HTTP 呼叫 | `circuit_breaker.py` |
| Database | asyncpg 連線池管理與 schema 初始化 | `database.py` |
| Schemas | Pydantic 模型，負責序列化/反序列化/驗證 | `schemas.py` |
| Metrics | Prometheus 指標定義與收集 | `metrics.py` |
| Config | 環境變數載入與組態管理 | `config.py` |

---

## 目錄結構

```
paper-catalog/
├── app/
│   ├── __init__.py              # Python 套件初始化（空）
│   ├── main.py                  # FastAPI 應用入口、路由、中介層、生命週期
│   ├── config.py                # Pydantic Settings 組態管理
│   ├── database.py              # asyncpg 連線池與 schema 初始化
│   ├── schemas.py               # Pydantic 請求/回應/事件模型
│   ├── kafka_consumer.py        # Kafka 事件消費者（背景任務）
│   ├── submission_client.py     # Submission Service HTTP Client
│   ├── circuit_breaker.py       # 自製非同步 Circuit Breaker
│   └── metrics.py               # Prometheus 指標定義
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI/CD Pipeline
├── Dockerfile                   # Multi-stage Docker 建置
├── pyproject.toml               # 專案元資料與依賴宣告（uv）
├── uv.lock                      # 依賴鎖定檔
├── .python-version              # Python 版本指定 (3.11)
└── .gitignore                   # Git 忽略規則
```

---

## 各模組詳細說明

### `app/main.py` — 應用入口

FastAPI 主程式，包含以下核心邏輯：

- **`lifespan(app)`**：非同步 context manager，管理服務啟動/關閉生命週期
  - 啟動時：建立 DB 連線池 → 初始化 schema → 建立 `SubmissionClient` → 啟動 Kafka Consumer 背景任務
  - 關閉時：關閉 Kafka Consumer → 關閉 `SubmissionClient` → 關閉 DB 連線池
- **`metrics_middleware`**：HTTP 中介層，記錄每個請求的 method、path、status code 及延遲至 Prometheus
- **`circuit_breaker_metrics_middleware`**：中介層，持續更新 Circuit Breaker 狀態指標

**路由端點**：

| 方法 | 路徑 | 功能 |
|---|---|---|
| GET | `/api/v1/catalog` | 列出所有館藏論文 |
| GET | `/api/v1/catalog/{paper_id}` | 查詢單一論文（優先從本地 DB，fallback 到 Submission Service） |
| GET | `/health` | 健康檢查 |
| GET | `/metrics` | Prometheus 指標端點 |

### `app/config.py` — 組態管理

使用 `pydantic-settings` 的 `BaseSettings` 自動從環境變數載入組態：

| 設定項 | 環境變數 | 預設值 | 說明 |
|---|---|---|---|
| `db_host` | `DB_HOST` | `localhost` | PostgreSQL 主機 |
| `db_port` | `DB_PORT` | `5432` | PostgreSQL 埠號 |
| `db_name` | `DB_NAME` | `catalog_db` | 資料庫名稱 |
| `db_user` | `DB_USER` | `postgres` | 資料庫使用者 |
| `db_password` | `DB_PASSWORD` | `postgres` | 資料庫密碼 |
| `kafka_bootstrap` | `KAFKA_BOOTSTRAP` | `localhost:9092` | Kafka Bootstrap Servers |
| `kafka_topic` | `KAFKA_TOPIC` | `paper-events` | 訂閱的 Kafka Topic |
| `kafka_group_id` | `KAFKA_GROUP_ID` | `catalog-consumer-group` | Kafka Consumer Group ID |
| `submission_service_url` | `SUBMISSION_SERVICE_URL` | `http://localhost:8081` | Submission Service 基礎 URL |
| `cb_max_failures` | `CB_MAX_FAILURES` | `5` | Circuit Breaker 最大失敗次數 |
| `cb_reset_timeout` | `CB_RESET_TIMEOUT` | `30.0` | Circuit Breaker 重置超時（秒） |
| `cb_call_timeout` | `CB_CALL_TIMEOUT` | `5.0` | 單次呼叫超時（秒） |

### `app/database.py` — 資料庫管理

- **`create_pool(settings)`**：建立 asyncpg 連線池（min=2, max=10）
- **`close_pool()`**：關閉連線池
- **`get_pool()`**：取得連線池實例
- **`init_db(pool)`**：初始化資料庫 schema，建立 `catalog_papers` 資料表

### `app/schemas.py` — Pydantic 模型

**`PaperCatalogResponse`**：API 回應模型

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `str` | 論文 UUID |
| `title` | `str` | 標題 |
| `author` | `str` | 作者 |
| `abstract_text` | `Optional[str]` | 摘要 |
| `status` | `Optional[str]` | 狀態 |
| `indexed_at` | `Optional[str]` | 索引建立時間 |

**`PaperCreatedEvent`**：Kafka 事件模型

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `str` | 論文 UUID |
| `title` | `str` | 標題 |
| `author` | `str` | 作者 |
| `abstractText` | `Optional[str]` | 摘要 |
| `status` | `Optional[str]` | 狀態 |
| `createdAt` | `Optional[str]` | 建立時間（ISO-8601） |

### `app/kafka_consumer.py` — Kafka 事件消費者

- **`start_consumer(pool, settings)`**：以背景任務啟動 aiokafka AIOKafkaConsumer
  - 訂閱 `paper-events` topic
  - 反序列化 JSON 訊息為 dict
  - 呼叫 `upsert_paper()` 寫入 DB
  - 內建 retry 邏輯：連線失敗時等待 5 秒重試
- **`upsert_paper(pool, event)`**：使用 `INSERT ... ON CONFLICT (id) DO UPDATE` 實現 upsert
  - 確保同一論文重複消費時不會產生重複資料（idempotent）

### `app/submission_client.py` — Submission Service Client

- **`SubmissionClient`**：封裝 httpx.AsyncClient，對 Submission Service 的 HTTP 呼叫加上 Circuit Breaker 保護
  - **`get_paper(paper_id)`**：透過 Circuit Breaker 呼叫 `GET /api/internal/papers/{paper_id}`
  - **`_fetch_paper(paper_id)`**：實際 HTTP 呼叫邏輯
  - **`close()`**：關閉 HTTP client

### `app/circuit_breaker.py` — 非同步 Circuit Breaker

自製的 async-native Circuit Breaker 實作：

**狀態機**：`CircuitState` enum — `CLOSED`, `OPEN`, `HALF_OPEN`

| 方法 | 功能 |
|---|---|
| `call(func, *args, **kwargs)` | 透過斷路器執行非同步函式，含超時控制 |
| `_record_failure()` | 記錄失敗，判斷是否需要跳脫至 OPEN |
| `_record_success()` | 記錄成功，HALF_OPEN 時可重置至 CLOSED |
| `_should_attempt_reset()` | OPEN 狀態下判斷是否已超過 `reset_timeout` |
| `get_state()` | 取得目前斷路器狀態 |

**組態參數**：

| 參數 | 預設值 | 說明 |
|---|---|---|
| `max_failures` | 5 | 連續失敗次數門檻 |
| `reset_timeout` | 30s | OPEN → HALF_OPEN 等待時間 |
| `call_timeout` | 5s | 單次呼叫超時時間 |

### `app/metrics.py` — Prometheus 指標

| 指標名稱 | 類型 | 標籤 | 說明 |
|---|---|---|---|
| `REQUEST_COUNT` | Counter | method, endpoint, status | HTTP 請求計數 |
| `REQUEST_LATENCY` | Histogram | method, endpoint | 請求延遲分佈 |
| `KAFKA_EVENTS_CONSUMED` | Counter | status | Kafka 事件消費計數 |
| `CIRCUIT_BREAKER_STATE` | Gauge | — | 斷路器狀態（0=CLOSED, 1=OPEN, 2=HALF_OPEN） |

---

## API 規格

### `GET /api/v1/catalog` — 列出所有館藏論文

**Response (200 OK):**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "A Study on Microservices",
    "author": "John Doe",
    "abstract_text": "This paper explores...",
    "status": "SUBMITTED",
    "indexed_at": "2026-02-11T10:30:05"
  }
]
```

**實作**：直接查詢本地 `catalog_papers` 資料表，回傳所有記錄。

---

### `GET /api/v1/catalog/{paper_id}` — 查詢單一論文

**Path Parameter:**

| 參數 | 型別 | 說明 |
|---|---|---|
| `paper_id` | String (UUID) | 論文唯一識別碼 |

**Response (200 OK):** 同上述 `PaperCatalogResponse` 結構。

**查詢策略（Fallback 機制）**：

```
1. 查詢本地 DB (catalog_papers)
   │
   ├── 找到 → 回傳結果
   │
   └── 找不到 → 透過 SubmissionClient 呼叫 Submission Service
                  │
                  ├── Circuit Breaker CLOSED → HTTP GET /api/internal/papers/{id}
                  │     │
                  │     ├── 成功 → 回傳結果
                  │     └── 失敗 → 記錄失敗 → 回傳 404
                  │
                  └── Circuit Breaker OPEN → 快速失敗 → 回傳 404
```

**Error (404):** 本地 DB 與 Submission Service 均查無資料。

---

### `GET /health` — 健康檢查

**Response (200 OK):**

```json
{
  "status": "healthy"
}
```

---

### `GET /metrics` — Prometheus 指標

回傳 Prometheus text format 的指標內容，供 Prometheus scraper 抓取。

---

## 資料模型

### `catalog_papers` 資料表 Schema

```sql
CREATE TABLE IF NOT EXISTS catalog_papers (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    author      TEXT NOT NULL,
    abstract_text TEXT,
    status      TEXT,
    indexed_at  TIMESTAMP DEFAULT NOW()
);
```

| 欄位 | 型別 | 約束 | 說明 |
|---|---|---|---|
| `id` | `TEXT` | PK | 論文 UUID（來自 Submission Service） |
| `title` | `TEXT` | NOT NULL | 論文標題 |
| `author` | `TEXT` | NOT NULL | 作者 |
| `abstract_text` | `TEXT` | nullable | 摘要 |
| `status` | `TEXT` | nullable | 論文狀態 |
| `indexed_at` | `TIMESTAMP` | default NOW() | 索引建立時間 |

**備註**：`id` 直接使用 Submission Service 產生的 UUID，確保跨服務資料一致性。Schema 由 `database.py` 的 `init_db()` 在服務啟動時自動建立。

---

## Kafka 事件消費機制

### 消費配置

| 屬性 | 值 |
|---|---|
| Topic | `paper-events` |
| Consumer Group | `catalog-consumer-group` |
| Kafka Client | aiokafka `AIOKafkaConsumer` |
| 反序列化 | JSON (UTF-8) |
| 寫入策略 | `INSERT ... ON CONFLICT DO UPDATE`（idempotent upsert） |

### 消費流程

```
Kafka Broker
    │
    ▼
AIOKafkaConsumer (background task)
    │ poll messages
    ▼
JSON Deserialize
    │
    ▼
upsert_paper(pool, event)
    │
    ▼
PostgreSQL: INSERT INTO catalog_papers ...
            ON CONFLICT (id) DO UPDATE
            SET title=..., author=..., ...
```

### 容錯機制

- **連線失敗**：Kafka Consumer 內建 retry，連線失敗時等待 5 秒後重試，不會導致服務崩潰
- **訊息處理失敗**：單一訊息處理失敗僅記錄 log，繼續消費後續訊息
- **冪等性**：使用 `ON CONFLICT DO UPDATE` 確保重複消費不會產生重複資料

---

## Circuit Breaker 容錯機制

### 狀態轉換

```
  CLOSED ──(連續 5 次失敗)──▶ OPEN ──(等待 30s)──▶ HALF_OPEN
    ▲                                                  │
    └──────────(呼叫成功)──────────────────────────────┘
                                                       │
                          OPEN ◀──(呼叫失敗)───────────┘
```

### 參數配置

| 參數 | 預設值 | 說明 |
|---|---|---|
| `max_failures` | 5 | 連續失敗達此次數後跳脫至 OPEN |
| `reset_timeout` | 30s | OPEN 狀態等待時間後嘗試 HALF_OPEN |
| `call_timeout` | 5s | 單次 HTTP 呼叫超時，超時視為失敗 |

### 保護對象

Circuit Breaker 保護的是 `SubmissionClient.get_paper()` 的 HTTP 呼叫。當 Submission Service 不可用時：

- **OPEN 狀態**：立即拋出 `CircuitBreakerOpenError`，不發送 HTTP 請求
- **效果**：避免大量超時請求拖垮 Catalog Service 的效能與執行緒資源
- **降級**：查詢 fallback 回 404，服務本身保持可用

---

## Prometheus 監控指標

### 可收集指標

| 指標 | 類型 | 說明 |
|---|---|---|
| `http_requests_total` | Counter | 按 method/endpoint/status 分組的請求總數 |
| `http_request_duration_seconds` | Histogram | 請求延遲分佈 |
| `kafka_events_consumed_total` | Counter | 按 status（success/error）分組的 Kafka 事件消費量 |
| `circuit_breaker_state` | Gauge | 斷路器狀態（0=CLOSED, 1=OPEN, 2=HALF_OPEN） |

### Scrape 配置

Helm Chart 已配置 Prometheus annotations：

```yaml
prometheus.io/scrape: "true"
prometheus.io/port: "8082"
prometheus.io/path: "/metrics"
```

---

## 組態設定

### 環境變數

| 變數 | 預設值 | 說明 |
|---|---|---|
| `DB_HOST` | `localhost` | PostgreSQL 主機位址 |
| `DB_PORT` | `5432` | PostgreSQL 埠號 |
| `DB_NAME` | `catalog_db` | 資料庫名稱 |
| `DB_USER` | `postgres` | 資料庫使用者 |
| `DB_PASSWORD` | `postgres` | 資料庫密碼 |
| `KAFKA_BOOTSTRAP` | `localhost:9092` | Kafka Bootstrap Servers |
| `KAFKA_TOPIC` | `paper-events` | 訂閱的 Kafka Topic |
| `KAFKA_GROUP_ID` | `catalog-consumer-group` | Consumer Group ID |
| `SUBMISSION_SERVICE_URL` | `http://localhost:8081` | Submission Service URL |
| `CB_MAX_FAILURES` | `5` | Circuit Breaker 最大失敗次數 |
| `CB_RESET_TIMEOUT` | `30.0` | Circuit Breaker 重置超時（秒） |
| `CB_CALL_TIMEOUT` | `5.0` | 單次呼叫超時（秒） |

### 相依服務

| 服務 | 用途 | 必要性 |
|---|---|---|
| PostgreSQL | 館藏資料持久化 | **必要** — 無法啟動 |
| Kafka | 事件消費（接收論文建立事件） | **非必要** — 消費失敗僅記錄 log，自動重試 |
| Submission Service | Fallback 查詢（本地 DB 查無資料時） | **非必要** — 查無時回傳 404 |

---

## 存取方式

### 1. Docker Compose（本地開發）

```bash
cd infra
docker compose up -d
# 服務可透過 http://localhost:8082 存取
curl http://localhost:8082/api/v1/catalog
```

### 2. Kubernetes + Istio（叢集部署）

**外部存取**（經由 Istio Gateway）：

```bash
curl http://<ISTIO_GATEWAY_IP>/api/v1/catalog
```

Istio VirtualService 路由規則將 `/api/v1/catalog` 導向 `catalog-service:8082`。

**叢集內部存取**（Service DNS）：

```bash
curl http://catalog-service.paper-demo.svc.cluster.local:8082/api/v1/catalog/{paper_id}
```

### 3. Helm 部署指令

```bash
# Dev 環境
helm upgrade --install catalog infra/helm-charts/paper-catalog \
  -f infra/helm-charts/paper-catalog/values-dev.yaml \
  -n paper-demo

# Production 環境
helm upgrade --install catalog infra/helm-charts/paper-catalog \
  -f infra/helm-charts/paper-catalog/values-prod.yaml \
  -n paper-demo
```

### 4. 一鍵部署腳本

```bash
./scripts/deploy-to-k8s.sh dev                           # 本地 dev 部署
./scripts/deploy-to-k8s.sh prod ghcr.io/user latest      # 遠端 registry 部署
```

---

## 效能分析

### 資源配置（依環境）

| 環境 | Replicas | CPU Request | CPU Limit | Memory Request | Memory Limit | HPA |
|---|---|---|---|---|---|---|
| Dev | 1 | 50m | 500m | 128Mi | 256Mi | 停用 |
| QA | 2 | 100m | 500m | 256Mi | 512Mi | 停用 |
| Prod | 3–10 | 200m | 1000m | 256Mi | 512Mi | 啟用 |

### HPA 自動擴展策略（Production）

| 指標 | 目標使用率 | 最小副本 | 最大副本 |
|---|---|---|---|
| CPU | 70% | 3 | 10 |
| Memory | 75% | 3 | 10 |

### 效能特性分析

#### 讀取路徑（GET /api/v1/catalog）

```
HTTP Request → asyncpg query (SELECT * FROM catalog_papers) → Pydantic serialize → HTTP Response
                      │
              ~1–5ms（全表掃描，資料量小時極快）
```

- **延遲**：全非同步 I/O，asyncpg 原生 PostgreSQL 協定，無 ORM 額外開銷
- **吞吐量**：單一實例約 1000–3000 QPS（FastAPI + uvicorn，受益於 async I/O）
- **注意事項**：無分頁機制，資料量增大時應加入 LIMIT/OFFSET

#### 讀取路徑（GET /api/v1/catalog/{paper_id}）

```
HTTP Request → asyncpg query (WHERE id = $1)
                      │
              ┌───────┴───────┐
              │ 找到           │ 找不到
              ▼               ▼
          回傳結果      SubmissionClient.get_paper()
                              │
                      Circuit Breaker 保護
                              │
                      ~5–50ms（含網路延遲）
```

- **本地查詢延遲**：~1–3ms（主鍵查詢）
- **Fallback 延遲**：~5–50ms（含跨服務 HTTP 呼叫）
- **Circuit Breaker OPEN 時**：~0ms（立即失敗，無等待）

#### Kafka 消費路徑

```
Kafka Message → JSON Deserialize → upsert_paper (INSERT ... ON CONFLICT)
                                          │
                                   ~2–10ms per message
```

- **消費延遲**：從事件產生到寫入 DB，通常 < 100ms（受 Kafka consumer poll interval 影響）
- **吞吐量**：單一 consumer 約 500–2000 msg/s

### 與 Submission Service 效能對比

| 面向 | Submission Service (Java) | Catalog Service (Python) |
|---|---|---|
| 冷啟動 | ~5–15s（JVM 啟動） | ~1–3s（Python 解譯器） |
| 記憶體佔用 | ~256–512Mi | ~128–256Mi |
| 單實例 QPS | ~500–1000 | ~1000–3000 |
| 非同步模型 | Thread pool（Tomcat） | Event loop（uvicorn/asyncio） |
| DB 存取 | JPA/Hibernate（ORM 開銷） | asyncpg（原生協定，零 ORM） |

### 可靠性設計

| 機制 | 實作 | 目的 |
|---|---|---|
| Startup Probe | `/health`, initialDelay=10s | 避免啟動未完成就接收流量 |
| Liveness Probe | `/health`, period=10s | 偵測服務異常並重啟 |
| Readiness Probe | `/health`, period=5s | 確保流量只導向就緒的 Pod |
| PDB | minAvailable=2 (prod) | 滾動更新時保證最低可用副本 |
| Circuit Breaker | 自製 async CB | Submission Service 故障時快速失敗 |
| Kafka Retry | 內建 5s 重連 | Kafka Broker 暫時不可用時自動恢復 |
| Idempotent Upsert | ON CONFLICT DO UPDATE | 重複消費不產生重複資料 |

### 已知限制與改善方向

| 項目 | 現況 | 建議改善 |
|---|---|---|
| 分頁查詢 | `SELECT *` 無分頁 | 加入 `LIMIT`/`OFFSET` 或 cursor-based pagination |
| 全文搜尋 | 無 | 加入 PostgreSQL `tsvector` 全文索引或整合 Elasticsearch |
| 快取 | 無 | 加入 Redis 快取熱點論文查詢 |
| Dead Letter Queue | 無 | Kafka 消費失敗訊息導入 DLQ 供後續處理 |
| 連線池監控 | 無 | 加入 asyncpg pool 使用率指標至 Prometheus |
| Schema Migration | `init_db()` 手動管理 | 整合 Alembic 進行版本化 migration |
| 認證授權 | 無 | 整合 OAuth2/JWT middleware |

---

## 建置與部署

### 本地開發

```bash
cd paper-catalog
uv sync                                 # 安裝依賴
uv run uvicorn app.main:app --reload    # 啟動開發伺服器
```

### Docker 建置

```bash
docker build -t paper-catalog:latest ./paper-catalog
```

Dockerfile 採用 `python:3.11-slim` 基底映像，使用 `uv` 安裝依賴，暴露 port 8082。

### CI/CD 建置與推送

```bash
./scripts/build-and-push.sh ghcr.io/<username> latest
```

---

## CI/CD Pipeline

GitHub Actions workflow（`.github/workflows/ci.yml`）：

| Job | 觸發條件 | 步驟 |
|---|---|---|
| lint-and-test | push/PR to main | 安裝依賴 → Lint → Test |
| docker | push to main | 建置 Docker image → 推送至 GHCR |

---

## 技術棧依賴版本

| 依賴 | 用途 |
|---|---|
| `fastapi` | 非同步 Web 框架 |
| `uvicorn` | ASGI 伺服器 |
| `asyncpg` | PostgreSQL 非同步驅動 |
| `aiokafka` | Kafka 非同步 Client |
| `httpx` | 非同步 HTTP Client |
| `pydantic` | 資料驗證與序列化 |
| `pydantic-settings` | 環境變數組態管理 |
| `prometheus-client` | Prometheus 指標收集 |
