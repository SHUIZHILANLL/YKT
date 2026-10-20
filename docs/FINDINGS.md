# 研究记录：证据、推翻与被证伪的假设

README 只留结论。这里留**过程**——包括本项目自己判断错的地方。

研究时间：2026 年 10 月，对象为**长江雨课堂** `changjiang.yuketang.cn`。

---

## 一、被推翻的三个判断（按时间顺序）

诚实比好看重要。以下三条都曾写进 README 当作结论。

### 1.1 「凭 sessionid 直连 `lesson-summary/student` 即可进班」→ 错

**原推理**：二维码里的 `sign` 只约束名单外的旁听生；在册学生凭 `sessionid` 已有该
`lesson_id` 的访问权，所以 `GET /api/v3/lesson-summary/student?lesson_id=X` 返回
`success:true` 就等于进班。

**实测**：真实课堂进行中，测 8 个变体：

```
GET  仅 Referer                   HTTP 200  code=0  data.errorCode=-1
GET  + Classroom-Id               HTTP 200  code=0  data.errorCode=-1
GET  + Accept: application/json   HTTP 200  code=0  data.errorCode=-1
GET  &source=14                   HTTP 200  code=0  data.errorCode=-1
GET  &source=14（无 Classroom-Id） HTTP 200  code=0  data.errorCode=-1
GET  &sign=&ts=                   HTTP 200  code=0  data.errorCode=-1
POST {source:14}                  HTTP 403  （Envoy 拦，该接口只收 GET）
POST {source:14,lesson_id}        HTTP 403
```

**全部 `errorCode: -1`。**

这里有个必须知道的坑：**该接口拒绝时顶层 `code` 仍然是 `0`**，真实结论在
`data.errorCode`。只看顶层 `code` 会把失败当成功——本项目早期就因此误报过
「已进班 / 课件 0 份」。

```json
{"code": 0, "data": {"errorCode": -1}}
```

### 1.2 「`lesson-summary/student` 是进班接口」→ 错

它在官方 App 的 `libapp.so` 字符串池里**出现 0 次**。214 条官方 API 路径中，
`/api/v3/lesson-summary/*` 整族属于**课后学习报告**（learning summary），
课进行中返回 `errorCode: -1` 属正常，与进班无关。详见 `GONGXIAOHU-ANALYSIS.md` 的对照。

### 1.3 「`X-Client: app` + Web 的 `Auth` 就能过 v3 业务层」→ 错

拿到官方 APK 后，查清了接口分族与**两层门**：

| 接口族 | 谁在用 | 网关要求 | 业务层凭证 |
|---|---|---|---|
| `/api/v3/lesson-summary/*` | PC 网页 | — | `cookie: sessionid` |
| `/api/v3/classroom/*` | 两端 | — | `cookie: sessionid`（实测 200） |
| `/api/v3/lesson/*` | **只有 App** | **`X-Client: app`** | **App 登录态** |

第一层门（同一个 `sessionid`，只改一个头）：

```
X-Client: web      → HTTP 401，无 Content-Type，
                     x-envoy-decorator-operation: cube-api-gateway...
X-Client: android  → HTTP 401
X-Client: ios      → HTTP 401
X-Client: app      → HTTP 200，application/json，code=50000
```

User-Agent（`okhttp` / `RainClassroom Android`）无影响，只有 `X-Client` 起作用。

第二层门当时没过去。以下**全部仍返回 50000**：

- `Authorization: Bearer / Token / JWT / Auth <_auth>`
- `Auth:` / `X-Auth:` / `X-Auth-Token:` / `X-Access-Token:` / `X-Token:` / `token:` 头
- `Authorization: Bearer <sessionid>`，以及 `Bearer <UserID>:<_auth>`
- `X-Session-Id:` / `Sessionid:` / `X-Sessionid:` 头
- `_auth` 或 `sessionid` 放进 Cookie
- `X-UID` 头（`UserID=<你的 userId>`）

当时据此写下「App 登录超出协议逆向范围」——**这条也被推翻**，见第二节。

---

## 二、真正的答案：`sid` cookie

### 2.1 怎么找到的

官方 APK 是 Flutter（`libapp.so`，sha256 `cb7f26f8…`，字符串池里 214 条 API 路径）。
在模拟器里装官方 App、登录自己的账号，然后**抓它自己的流量**。

Flutter 的 `dart:io` **不读 Android 系统代理**，CONNECT 代理一条都抓不到。可行做法：

1. 模拟器 `adb root`
2. `openssl` 自签 CA + 该域名的服务端证书
3. `mount --bind` 覆盖 `/system/etc/security/cacerts`
   （Android 15 无法 remount `/system`，但 bind mount 可行）
4. `adb reverse tcp:8081 tcp:8081`
5. `iptables -t nat -A OUTPUT -p tcp -d <yuketang IP> --dport 443 -j REDIRECT --to-ports 8081`
6. 本机跑只转发该域名的 TLS 终结代理
7. 在 App 里操作几下，从日志读 `cookie:` 行

### 2.2 抓到的真实请求头

```
user-agent: Android
x-client: app
xtua: client=app&tag=1.3.5&platform=Android
version: 1.3.5
brand / systemversion / buildnumber / incremental / isphysicaldevice
xtbz: ykt
x-uid: <userId>
cookie: sessionid=<…>; sid=<…>; csrftoken=<…>; django_language=zh-cn
```

**没有任何 `Authorization` 头。** 纯 cookie 鉴权，也没有请求签名。

### 2.3 关键对照实验

```
cookie "sessionid=X"          -> code 50000 UNAUTHENTICATED
cookie "sessionid=X; sid=Y"   -> code 0
```

再进一步：

```
app sessionid + app sid  -> code 0
web sessionid + app sid  -> code 0     ← sid 与 sessionid 不绑定
app sessionid + 无 sid   -> code 50000
```

所以 **`sid` 是独立凭证**，Web 扫码登录拿不到它，只能来自 App 登录。

### 2.4 可用的签到调用

```
POST /api/v3/lesson/checkin
body {"source":23, "lessonId":"<字符串>", "joinIfNotIn":true}
cookie: sessionid=<任意有效会话>; sid=<App 的 sid>
```

返回：

```json
{"code":0,"msg":"OK","data":{
  "role":5,
  "lessonId":"…",
  "lessonToken":"eyJ0eXAiOiJKV1Qi…",
  "identityId":"…",
  "identityName":"…",
  "identityNumber":"…"
}}
```

`lessonToken` 是服务端签发的 JWT（HS256），payload 含
`lessonId / userId / identityId / iat / exp`，有效期 **6 小时**，供后续课件、弹幕、答题使用。

### 2.5 两个坑

| 坑 | 后果 |
|---|---|
| `lessonId` 传**数字** | `50400 BAD_REQUEST`，必须传字符串 |
| 请求带 `Authorization` 头 | 同样 `50400`。必须用与官方 App 一致的干净请求头 |

另外：**用带 cookie jar 的 Session 复用请求头也会失败**，这个接口要一次独立的干净请求。

---

## 三、旧路径（已废弃，仅存档）

| 端点 | 结果 | 说明 |
|---|---|---|
| `/api/v3/lesson/notkn/checkin` | `50002 LESSON_UNAUTHORIZED` | 官方 App 里**不存在**这个端点 |
| `/api/v3/lesson/checkin` `{source:14}` | `50002 LESSON_UNAUTHORIZED` | 缺 sid，且没有 joinIfNotIn |
| `/api/v3/lesson-summary/checkin` | Envoy 直接拒 | 无 Content-Type、只有 `x-envoy-*` 头、403/500 随形状跳变 |
| `/api/lesson/web_check_in` | — | 网页端旧接口，需 `X-CSRFToken`，非 5 位码路径 |

`LESSON_UNAUTHORIZED` 的含义是「缺课堂上下文」，而课堂上下文是**签到成功后**才下发的——
当时以为这是闭环，实际上只要有 `sid` + `joinIfNotIn` 一步就解开了。

带暗号的网页端逻辑（bundle `@5201763`）仍然有效，但已非首选：

```js
if (5 !== code.length) return 走 join_classroom;   // 不是 5 位 → 班级邀请码
if (/[0-9]/.test(code.charAt(0))) return checkin(14, code);   // 首位数字 → 新接口
r = { invite_code: code, source: 14 };             // 否则 → 旧接口
```

---

## 四、开课检测：一条踩过的坑

`正在上课` 的数据源**不是** `/v/course_meta/on_lesson_courses`——那个端点无论登录与否都返回
`{"success":true,"data":{"on_lessons":[]}}`，看着像成功，实际永远是空的。

真实来源是 `/api/v3/classroom/on-lesson-upcoming-exam`，读 `data.onLessonClassrooms`。
这是从 PC 端 bundle 的解析代码倒推出来的：

```js
e = API.pc.index.on_lesson_upcoming_exam      // /api/v3/classroom/on-lesson-upcoming-exam
if ((n = await get(e)).code === 0) {
  l = n.data.onLessonClassrooms ?? []         // ← 正在上课的课堂
  u = n.data.upcomingExam ?? []
  lessonList = l.map(x => Object.assign(x, { id: x.lessonId, isV3: true }))
}
```

条目字段：`courseName`、`classroomName`、`lessonId`、`classroomId`、`courseId`、
`role`（1/2 为教师侧，其余为学生）、`openTeacher`。

---

## 五、端点状态总表

| 端点 | 方法 | 状态 | 说明 |
|---|---|---|---|
| `/api/v3/classroom/on-lesson-upcoming-exam` | GET | ✅ | 正在上课的数据源，读 `data.onLessonClassrooms` |
| `/v2/api/web/courses/list?identity=2` | GET | ✅ | 课程列表，要 `sessionid` |
| `/v2/api/web/logs/learn/{cid}?actype=-1&page=0&offset=500&sort=-1` | GET | ✅ | 课次列表（`offset` 实际是 PageSize） |
| `/api/v3/user/basic-info` | GET | ✅ | 判活 |
| **`/api/v3/lesson/checkin`** | POST | ✅ | **App 形态 `{source:23, lessonId:"串", joinIfNotIn:true}`** |
| `/api/v3/lesson-summary/student` | GET | ❌ | 课后报告，非进班；拒绝时顶层 `code` 仍为 0 |
| `/v/course_meta/on_lesson_courses` | GET | ⚠️ | 永远返回空数组，仅作兜底 |
| `/api/v3/lesson/notkn/checkin` | POST | ❌ | 官方 App 无此端点 |
| `/api/v3/lesson-summary/checkin` | POST | ❌ | Envoy 拒绝 |
| `/api/v3/user/login/app` | POST | ⚠️ | 需验证码 + 图形验证 `ticket`，是本项目未自动化的部分 |

---

## 六、与那篇文章的差异

| 文章说法 | 实际 |
|---|---|
| `/custom/auth/v1/auth/status` 30 秒阻塞长轮询 | 该路径在三个域名下都不存在。PC 网页端登录走 WebSocket |
| `get_user_course_list` 查课表 | 真实接口是 `/v2/api/web/courses/list?identity=2` |
| 过滤 `status == 1` 判断开课 | 真实接口是 `on_lesson_courses` 返回 `on_lessons` 数组 |
| 扫码进班链接是临时签名链接 | 前半句对；「签名只约束旁听生、在册学生不需要」**未获证实** |

需要说明：文章说的长轮询其实是他**自建网关** `hnit.jiclub.site` 的
`POST /api/ykt/auth/login-qr`，而 PC 网页端确实是 WebSocket。两者都对，是两个不同的客户端。
详见 `GONGXIAOHU-ANALYSIS.md`。
