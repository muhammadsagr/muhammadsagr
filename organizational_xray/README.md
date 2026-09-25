# 🩻 Organizational X-Ray

نظام لتحليل الهيكل التنظيمي يعمل كـ"أشعة سينية" للمنظمة: يحمّل بيانات الموظفين، يبني شبكة العلاقات الإدارية، ويحلل الطبقات و Span of Control والإدارات والعلاقات غير الصحيحة وجودة البيانات، ثم يحوّل كل ذلك إلى **Findings قابلة للتفسير** مع **What-If Simulator** لتجربة التغييرات قبل تطبيقها.

```
Data → Rules → Calculations → Evidence → Findings → Visualization
```

كل رقم في الواجهة محسوب من البيانات، وكل Finding يعرض القاعدة، والقيمة، والحد المحدد، والمرجع التنظيمي، والسجلات المصدرية. لا تعتبر أي ملاحظة حكمًا نهائيًا: الصياغة دائمًا «تم اكتشاف … ويحتاج إلى مراجعة».

---

## التشغيل

المتطلبات: Python 3.12+ (يعمل أيضًا على 3.11).

```bash
cd organizational_xray
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

يفتح التطبيق على `http://localhost:8501` ويحلل البيانات الوهمية (~1,500 موظف) مباشرة — بدون قاعدة بيانات أو API خارجي.

الاختبارات:

```bash
pytest
```

إعادة إنشاء ملف البيانات الوهمية وطباعة تقرير محسوب منه:

```bash
python -m data.dummy_generator                 # 1,500 موظف، seed 42
python -m data.dummy_generator --employees 10000 --seed 7 --no-save
```

---

## الصفحات

| الصفحة | ماذا تعرض |
|---|---|
| **Dashboard** | 9 بطاقات KPI، «إجابات الأشعة السينية» (أسئلة الهيكل الأساسية مع الدليل الرقمي)، توزيع الطبقات والإدارات و Span of Control، والهيكل BU → Division → Department |
| **Layers** | الطبقات حسب Job Level (المعلن) وحسب العمق الفعلي، إحصاءات Depth (Min/Max/Mean/Median)، مصفوفة Job Level × Depth، أطول Reporting Chains، والعمق لكل موظف |
| **Span of Control** | Min / Max / Mean / Median / P25 / P75، Histogram تفاعلي بحدود قابلة للتعديل، جدول المديرين مع التصنيف، وتحليل حسب الإدارة والمستوى |
| **Departments** | لكل إدارة: Headcount، المديرون، Management Ratio، Avg Span، Avg Depth، الشواغر، متوسط ووسيط الراتب، عدد الطبقات — مع بحث وتصفية وفرز، وعرض للقطاعات ووحدات الأعمال، و Job Titles (مكررة / متشابهة) |
| **Organization Map** | شبكة Employee → Manager (NetworkX + Plotly) بنطاقات: Entire Organization / Business Unit / Division / Department / Specific Manager، مع حد أقصى للعقد حتى يبقى الرسم مقروءًا |
| **Employee Explorer** | بحث بالرقم أو الاسم، السلسلة الإدارية للأعلى (تكتشف الحلقات والانقطاعات)، Direct / Indirect Reports، والـFindings المرتبطة |
| **X-Ray Findings** | كل الملاحظات مع Finding ID، Type، Severity، الكيان، Description، Evidence، Recommended Investigation، وعند اختيار أي صف: القاعدة والقيمة والحد والمرجع والسجلات المصدرية |
| **Data Quality** | Completeness / Uniqueness / Validity / Consistency / Referential Integrity — اختر أي مقياس لعرض السجلات المتأثرة |
| **What-If Simulator** | دمج إدارات، إزالة طبقة إدارية، نقل موظف، إزالة مدير (مع اختيار المستلم) — يمكن جمعها في سيناريو واحد، ثم Before / After و«ما الذي تغير؟» |
| **Import Data** | رفع CSV / Excel مع Validation ومطابقة تلقائية لأسماء الأعمدة، قوالب للتحميل، وتوليد بيانات وهمية بأحجام 1.5k – 10k |
| **Export** | ملف Excel بالأوراق: Employees، Managers، Departments، Findings، Span of Control، Organizational Layers، Data Quality — وكل جدول في التطبيق له زر CSV |
| **Settings** | Low Span = 3، High Span = 12، Deep Hierarchy = 6، Small Department = 3، High Management Ratio = 20%، Title Similarity = 0.80 |

**Global Filters** في الشريط الجانبي (Business Unit، Division، Department، Location، Job Level، Employment Status، Employment Type، Manager) تؤثر على الأرقام والرسومات والـFindings. الهيكل نفسه يُحسب دائمًا على كامل البيانات (حتى يكون العمق صحيحًا) ثم تُطبق الفلاتر على النتائج.

---

## التعريفات والقواعد

| المفهوم | التعريف |
|---|---|
| Employee (Headcount) | سجل بوظيفة مشغولة وحالة Active أو On Leave |
| Manager | موظف نشط لديه موظف مباشر نشط واحد على الأقل |
| Span of Control | عدد الموظفين المباشرين النشطين (الوظائف الشاغرة تُعرض منفصلة) |
| Depth | عدد العلاقات الإدارية بين الموظف والـCEO (CEO = 0) |
| Layers | عدد مستويات العمق المختلفة بين الموظفين المتصلين بالـCEO |
| Management Ratio | المديرون ÷ إجمالي الموظفين |
| Vacancy Rate | الوظائف الشاغرة ÷ (الشاغرة + المشغولة) |

| Finding | القاعدة (القيم الافتراضية) | Severity |
|---|---|---|
| LOW_SPAN_OF_CONTROL | Direct Reports ≤ 3 (استثناء CEO و C-Suite قابل للتعديل) | Attention (1) / Informational |
| HIGH_SPAN_OF_CONTROL | Direct Reports > 12 | Attention ≤1.5× · Significant ≤2.5× · Critical |
| DEEP_HIERARCHY | عمق موظفي الإدارة > 6 | Attention / Significant |
| ORPHAN_EMPLOYEE | Manager ID فارغ وليس الـCEO | Significant |
| INVALID_MANAGER | Manager ID غير موجود | Significant |
| TERMINATED_MANAGER | المدير حالته Terminated | Significant |
| CIRCULAR_REPORTING | حلقة في الرسم البياني (Strongly Connected Component أو Self-loop) | Critical |
| SMALL_DEPARTMENT | Headcount ≤ 3 | Informational / Attention (0) |
| HIGH_MANAGEMENT_RATIO | Management Ratio > 20% (للإدارات الأكبر من حد الإدارة الصغيرة) | Attention / Significant |
| VACANT_POSITION | Position Status = Vacant، أو مدير كل فريقه شاغر | Informational / Attention |
| DUPLICATE_POSITION | Position ID مكرر، مسمى بصيغ كتابة مختلفة، أو مسميات متشابهة نصيًا داخل نفس القطاع | Significant / Attention / Informational |

التشابه النصي للمسميات لا يعتمد على تشابه الحروف فقط (الذي يربط خطأً بين «Brand Specialist» و «HR Specialist»)، بل على: اختصارات (L&D ↔ Learning & Development)، أو احتواء كلمات أحد المسميين في الآخر، أو اختلاف كلمة واحدة متشابهة. أزواج السلم الوظيفي (Accountant / Senior Accountant) لا تُعد تكرارًا.

---

## البيانات الوهمية

يتم **بناء الهيكل أولًا** (Blueprint لكل إدارة: عدد الطبقات والفرق ونطاق الإشراف ونسبة الشواغر)، ثم توليد الأشخاص بـ Faker ووضعهم في الوظائف، ثم إدخال مشكلات متعمدة وتسجيلها في Manifest. الإدارات مختلفة عمدًا: Operations عميقة جدًا (CEO → COO → VP → Senior Director → Director → Senior Manager → Manager → Supervisor → Employee)، بينما Business Development مسطحة (Director → موظفون)، و HRIS كثيفة المديرين، و Quality يديرها Director بـ17 موظفًا مباشرًا.

**الأرقام الفعلية تُحسب ديناميكيًا** — من صفحة Import Data ← «وصف البيانات الحالية»، أو بالأمر `python -m data.dummy_generator` الذي يكتب التقرير. نسخة من التقرير للـseed الافتراضي في [DATASET.md](DATASET.md)، وملخصها:

- ~1,474 موظف نشط، 66 وظيفة شاغرة، 222 مديرًا، 24 إدارة في 7 قطاعات و4 وحدات أعمال
- 9 طبقات هيكلية (عمق 1–8)، Span of Control: وسيط 6، متوسط 6.5، من 1 إلى 32
- ~199 Finding بالإعدادات الافتراضية

**المشكلات المُدخلة عمدًا والنتائج المتوقعة:**

| المشكلة | النتيجة المتوقعة |
|---|---|
| تسلسل عميق في Operations مقابل إدارات مسطحة | DEEP_HIERARCHY (Operations)، ومصفوفة Job Level × Depth تكشف تكرار مستوى Directors |
| مديرون بـ1 و2 و3 موظفين (HRIS، Procurement، Cybersecurity، Treasury …) | LOW_SPAN_OF_CONTROL |
| مشرفون بـ15 و20 و22 و30+ موظفًا، و Director Quality بـ17 | HIGH_SPAN_OF_CONTROL |
| 3 موظفين بدون Manager ID | ORPHAN_EMPLOYEE |
| 3 موظفين بـ Manager ID غير موجود | INVALID_MANAGER |
| مديران Terminated ما زال فريقهما يتبعهما | TERMINATED_MANAGER + فحص اتساق في Data Quality |
| حلقة A → B → C → A في Marketing، وموظف مدير لنفسه | CIRCULAR_REPORTING (بدون Crash) |
| مسميات HR Analyst / hr analyst / HRIS Analyst / Hris Analyst / HR Data Analyst / L&D Specialist … | DUPLICATE_POSITION (صيغ مكررة ومسميات متشابهة) |
| Position IDs مكررة (زوجان) | DUPLICATE_POSITION |
| Total Rewards (3)، Treasury (2)، Internal Audit (3)، Strategy Office (1)، و ESG بوظائف شاغرة فقط | SMALL_DEPARTMENT |
| HRIS: 9 مديرين من 15 موظفًا | HIGH_MANAGEMENT_RATIO |
| شواغر بنسب مختلفة لكل إدارة، و Team Lead كل فريقه شاغر | VACANT_POSITION |
| Employee ID مكرر، مسميات/رواتب/إدارة مفقودة، راتب = 0 | Data Quality |

اختبار `tests/test_anomalies.py::test_dummy_detects_every_injected_issue` يتحقق أن كل مشكلة في الـManifest يتم اكتشافها.

---

## هيكل المشروع

```
organizational_xray/
├── app.py                     # نقطة الدخول: streamlit run app.py
├── data/
│   ├── dummy_generator.py     # بناء الهيكل + Faker + المشكلات المتعمدة + Manifest
│   ├── loader.py              # قراءة CSV/Excel وتوحيد الأعمدة والقيم
│   ├── validator.py           # Validation عند الاستيراد
│   └── sample/                # org_dummy_data.csv / .xlsx
├── analytics/                 # Business logic فقط (بدون Streamlit)
│   ├── hierarchy.py           # الرسم البياني، CEO، Depth، الحلقات، حالة العلاقة الإدارية
│   ├── span_of_control.py
│   ├── departments.py         # مقاييس الوحدات والطبقات والمسميات
│   ├── anomalies.py           # X-Ray Findings Engine
│   ├── data_quality.py
│   ├── simulations.py         # What-If (سيناريو = قائمة إجراءات JSON)
│   ├── insights.py            # إجابات الأسئلة الأساسية مع الدليل
│   ├── engine.py              # OrgXRayEngine + TOOL_SPECS للـAI مستقبلًا
│   └── report.py              # تقرير البيانات المحسوب
├── visualization/             # Plotly figures (theme، hierarchy، departments، network، dashboards)
├── ui/                        # صفحات Streamlit + state/caching + مكونات مشتركة
├── utils/                     # config (الحدود والمخطط) + helpers
├── exports/exporter.py        # Excel متعدد الأوراق و CSV
└── tests/                     # pytest
```

**الأداء:** الهيكل يُبنى مرة واحدة لكل مجموعة بيانات (`st.cache_resource`)، والـFindings وجودة البيانات تُخزن حسب (البيانات، الإعدادات)؛ تغيير الفلاتر أو الصفحة لا يعيد الحساب. كل الخوارزميات خطية (BFS، Condensation للحلقات، تخطيط شجري بدون Recursion). مثال: 10,000 موظف ← بناء الهيكل ~0.7 ثانية، الـFindings ~0.4 ثانية.

---

## تجهيز المشروع لمساعد AI

`analytics/engine.py` يوفر `OrgXRayEngine` وقائمة `TOOL_SPECS` (بصيغة JSON Schema) و `call_tool()`. المساعد المستقبلي يجب أن **يستدعي هذه الأدوات** ثم يصيغ النتيجة، ولا يحسب الأرقام بنفسه:

| سؤال المستخدم | الأداة |
|---|---|
| ما الإدارات التي لديها أعلى Management Ratio؟ | `departments_by(metric="management_ratio")` |
| اعرض المديرين الذين لديهم أقل من 3 موظفين مباشرين | `managers_by_span(max_reports=2)` |
| ماذا سيحدث لو دمجنا HRIS و HR Operations؟ | `simulate(actions=[{"type": "merge_departments", ...}])` |
| لماذا تم تصنيف هذا القسم كـ Deep Hierarchy؟ | `explain_department("Operations")` / `explain("F-0014")` |
| اعرض أطول Reporting Chains | `longest_reporting_chains(top=10)` |

```python
from analytics.engine import OrgXRayEngine, call_tool
import pandas as pd

engine = OrgXRayEngine(pd.read_csv("data/sample/org_dummy_data.csv", dtype=str))
call_tool(engine, "departments_by", {"metric": "management_ratio", "top": 3})
```

---

## استيراد بياناتك

الحقول الأساسية: `EmployeeID, EmployeeName, ManagerID, JobTitle, Department, Division, BusinessUnit, JobLevel, Salary, EmploymentStatus, PositionID, PositionStatus` (والحقول الإضافية اختيارية). أسماء الأعمدة الشائعة تُطابق تلقائيًا (`Employee ID`، `employee_id`، `Reports To`، `رقم الموظف` …). الوظيفة الشاغرة = صف بدون EmployeeID مع `PositionStatus = Vacant`. غياب `EmployeeID` أو `ManagerID` يمنع التحليل؛ باقي المشكلات تُعرض كتحذيرات ولا توقف البرنامج.
