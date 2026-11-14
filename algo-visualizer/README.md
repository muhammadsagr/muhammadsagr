# ⟨/⟩ مُصوِّر الخوارزميات: Algorithms × DevOps × Cloud

منصة تفاعلية تعرض الخوارزميات خطوة بخطوة، وتجمع بين:
1. **الخوارزميات الكلاسيكية:** الترتيب وإيجاد المسار مع قياس التعقيد الفعلي.
2. **الخوارزميات التي تشغّل السحابة نفسها:** موازنة الأحمال، و Consistent Hashing، وجدولة خطوط CI/CD، و Autoscaling، و Rate Limiting.
3. **بنية DevOps كاملة حول التطبيق:** Docker، و CI/CD، و Kubernetes، و Terraform، والمراقبة بـ Prometheus و Grafana.

> بلا أي مكتبات خارجية: Node.js فقط. نفس ملفات الخوارزميات تعمل في المتصفح (للعرض المتحرك) وعلى الخادم (للـ API والقياس).

---

## 🚀 التشغيل السريع

### الأسهل: بدون تثبيت أي شيء
افتح الملف **`algo_visualizer.html`** الموجود في جذر المستودع بالضغط عليه مرتين، فيفتح في المتصفح مباشرة وتعمل كل الخوارزميات داخله.

> ⚠️ لا تفتح `public/index.html` مباشرة، فهو يحتاج الخادم (المتصفح يمنع تحميل ملفات JavaScript من `file://`).
> بعد أي تعديل على `public/` أو `src/core/` أعِد توليد الملف بالأمر `npm run build:standalone`.

### محلياً (Node.js 20+)
```bash
cd algo-visualizer
npm start          # http://localhost:8080
npm test           # 42 اختباراً
```

### Docker
```bash
docker build -t algo-visualizer .
docker run -p 8080:8080 algo-visualizer
```

### "سحابة مصغّرة" على جهازك (3 نسخ + موازن أحمال + مراقبة)
```bash
docker compose up --build
```
| الخدمة | الرابط |
|---|---|
| التطبيق (عبر nginx) | http://localhost:8080 |
| Prometheus | http://localhost:9090 |
| Grafana (لوحة "Algo Visualizer") | http://localhost:3000 |

> حدّث الصفحة عدة مرات وراقب الشارة أعلى اليسار: ستتغير لأن طلباتك توزَّع على 3 نسخ مختلفة.

---

## 🧠 الخوارزميات

| التبويب | الخوارزميات | المفاهيم |
|---|---|---|
| 📊 الترتيب | Bubble, Selection, Insertion, Shell, Merge, Quick, Heap | التعقيد، الاستقرار، أفضل وأسوأ حالة، Divide & Conquer |
| 🧭 إيجاد المسار | BFS, DFS, Dijkstra, A* | Graphs، Priority Queue (Binary Heap)، Heuristics، الشبكات الموزونة |
| ⚙️ خط CI/CD | Kahn's Topological Sort + Critical Path | DAG، كشف الدورات، البرمجة الديناميكية، التوازي |
| ⚖️ موازنة الأحمال | Round Robin, Smooth Weighted RR (nginx), Least Connections, Random, Power of Two Choices | Discrete-event simulation، زمن الاستجابة p95/p99 (tail latency) |
| 💍 Consistent Hashing | Hash ring + Virtual nodes + Binary search | التوزيع، إعادة التوازن، مقارنة مع `hash % N` |
| 📈 Autoscaling | معادلة Kubernetes HPA | حلقات التحكم، هامش التسامح، التكلفة مقابل الأداء |
| ⏱️ قياس التعقيد | قياس على الخادم عبر API | O(n²) مقابل O(n log n) بأرقام حقيقية |
| (في الخادم) | Token Bucket | Rate limiting لكل عنوان IP |

---

## ☁️ خريطة مفاهيم DevOps و Cloud في المشروع

| المفهوم | أين تجده؟ |
|---|---|
| **Containerization** و Multi-stage build | `Dockerfile`: الاختبارات تعمل داخل البناء، والصورة النهائية صغيرة وتعمل بمستخدم غير root |
| **Health checks** (liveness و readiness) | `/healthz` و `/readyz` في `src/app.js`، و `HEALTHCHECK` في Dockerfile، والـ probes في `k8s/deployment.yaml` |
| **Graceful shutdown** | `src/server.js`: عند SIGTERM تفشل readiness أولاً، ثم تُكمَل الطلبات الجارية قبل الإغلاق |
| **12-Factor config** | كل الإعدادات عبر متغيرات البيئة: `PORT`، `RATE_LIMIT_RPS`، `CLOUD_REGION`… و ConfigMap في k8s |
| **Observability**: Metrics | `/metrics` بصيغة Prometheus (عدّاد طلبات، histogram زمن الاستجابة، عدد تشغيل الخوارزميات) من `src/metrics.js` |
| **Observability**: Logs | سجلات JSON منظمة (structured logging) |
| **Alerting و SLO** | `deploy/prometheus/alerts.yml`: نسبة الأخطاء، و p95، وتعطل نسخة |
| **Dashboards** | Grafana مُعدّة تلقائياً (provisioning) في `deploy/grafana/` |
| **Load balancing** | nginx بـ `least_conn` في `deploy/nginx/nginx.conf`، وفي k8s عبر Service و Ingress |
| **Service discovery** | Prometheus يكتشف النسخ عبر DNS (`dns_sd_configs`) |
| **Rate limiting** | Token Bucket في التطبيق + `limit_req` في nginx + annotation في Ingress |
| **CI** | `.github/workflows/algo-visualizer.yml`: اختبارات على Node 20 و 22، وفحص الكود، والتحقق من k8s و Terraform |
| **Security scanning (DevSecOps)** | Trivy يفحص الصورة ويرفع النتائج إلى GitHub Security، و ECR يفحص الصورة عند الرفع |
| **CD** | دفع الصورة إلى GHCR، ثم Rolling update على Kubernetes مع موافقة يدوية (environment) و rollback تلقائي |
| **Kubernetes** | `k8s/`: Deployment و Service و Ingress (TLS) و HPA و PDB و NetworkPolicy مع Kustomize |
| **Zero-downtime deploys** | `maxUnavailable: 0` + readiness + `preStop` + PodDisruptionBudget |
| **High availability** | 3 نسخ موزّعة على مناطق التوفر (`topologySpreadConstraints`) |
| **Autoscaling** | `k8s/hpa.yaml` و App Runner autoscaling في Terraform |
| **Security hardening** | non-root، و read-only filesystem، وإسقاط كل الـ capabilities، و seccomp، و Pod Security "restricted"، و CSP headers، وحماية من path traversal |
| **Infrastructure as Code** | `terraform/`: ECR + IAM + App Runner (serverless containers) + CloudWatch alarm على AWS |

---

## 🔌 الـ API

| Method | المسار | الوصف |
|---|---|---|
| GET | `/api/info` | النسخة والـ Pod والمنطقة |
| GET | `/api/algorithms` | فهرس الخوارزميات وتعقيدها |
| POST | `/api/sort` | `{algorithm, array, includeSteps}` |
| POST | `/api/pathfind` | `{algorithm, grid:{rows,cols,walls,weights,start,end}}` |
| GET | `/api/benchmark?algorithm=quick&input=random&sizes=100,200` | قياس عدد العمليات والزمن |
| POST | `/api/pipeline` | جدولة DAG (بدون جسم الطلب = خط CI/CD الافتراضي) |
| POST | `/api/loadbalance` | `{servers:[{id,capacity}], strategy, requestCount}` |
| POST | `/api/hashring` | `{before:[...], after:[...], keys, virtualNodes}` |
| POST | `/api/autoscale` | `{load:[...], targetPerPod, min, max}` |
| GET | `/healthz`, `/readyz`, `/metrics` | للبنية التحتية |

```bash
curl -X POST localhost:8080/api/hashring -H 'content-type: application/json' \
  -d '{"before":["a","b","c","d"],"after":["a","b","c","d","e"],"keys":5000}'
```

---

## ☸️ النشر على Kubernetes
```bash
kubectl apply -k k8s/
kubectl -n algo-visualizer get pods,hpa
kubectl -n algo-visualizer rollout status deployment/algo-visualizer
```
عدّل `algo.example.com` في `k8s/ingress.yaml` إلى نطاقك. يتطلب ingress-nginx و cert-manager و metrics-server (لعمل الـ HPA). خاصية `preStop.sleep` تحتاج Kubernetes 1.30 أو أحدث.

## 🏗️ النشر على AWS بـ Terraform
```bash
cd terraform
terraform init
terraform apply -target=aws_ecr_repository.app   # 1) أنشئ السجل أولاً
```
ادفع الصورة إلى `ecr_repository_url` من المخرجات، ثم:
```bash
terraform apply -var image_tag=<tag>
```
الرابط العام يظهر في المخرج `service_url`.

## 🔁 CI/CD
- كل Pull Request: اختبارات، وفحص صيغة الكود، والتحقق من k8s و Terraform، وبناء الصورة، و smoke test، وفحص Trivy.
- كل دفع إلى `main`: ما سبق، ثم دفع الصورة إلى GHCR.
- النشر التلقائي على Kubernetes اختياري: أضف متغير المستودع `DEPLOY_ENABLED=true` والـ secret المسمى `KUBECONFIG`.

---

## 📁 هيكل المشروع
```
algo-visualizer/
├── src/
│   ├── core/            # الخوارزميات (مشتركة بين المتصفح والخادم)
│   │   ├── sorting.js   pathfinding.js   cloud.js   heap.js   random.js   benchmark.js
│   ├── app.js           # HTTP API + static + metrics + rate limiting
│   ├── metrics.js       # Prometheus exposition format
│   └── server.js        # التشغيل + graceful shutdown
├── public/              # الواجهة (HTML/CSS/JS بدون build step)
├── test/                # node:test (خوارزميات + API)
├── Dockerfile  docker-compose.yml
├── deploy/              # nginx, prometheus (+alerts), grafana
├── k8s/                 # Kustomize manifests
└── terraform/           # AWS ECR + App Runner
```

## 🛣️ أفكار للتطوير
- محرر كود يكتب فيه المستخدم خوارزميته وتُنفَّذ في **sandbox** (Web Worker أو حاوية معزولة) ثم تُعرض.
- تخزين الجلسات والنتائج في **Redis/PostgreSQL** مع Helm chart.
- **Distributed tracing** عبر OpenTelemetry.
- **Canary deployments** عبر Argo Rollouts، و GitOps عبر Argo CD.
- خوارزميات توزيع إضافية: Raft (انتخاب القائد)، و Gossip protocol، و Bloom filters، و Merkle trees.
