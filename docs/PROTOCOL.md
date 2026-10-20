# 雨课堂协议规格（可复现版）

这份文档的目标是：**不提供任何客户端程序**，只把协议事实写清楚到「一个了解 HTTP 的
工程师（或 AI）照着就能自己实现」的程度。

研究对象：**长江雨课堂** `changjiang.yuketang.cn`（PC 网页端 + Android 官方 App 1.3.5）。
全部结论来自 2026-10 的静态提取、真机抓包与真实课堂实测；证据与推翻过程见
[FINDINGS.md](FINDINGS.md)。

> 阅读前提：本文描述的是**平台既有的、官方客户端自己也在用**的接口行为。
> 复现它意味着你自己调用这些接口，风险（账号、纪律、法律）自负，见 [../SECURITY.md](../SECURITY.md)。

---

## 1. 后端与域名

| 名称 | 基址 | 说明 |
|---|---|---|
| 长江雨课堂 | `https://changjiang.yuketang.cn` | 本项目的研究对象，根路径 302 → `/web` |
| 长江别名 | `https://changjiang.ykt.io` | 指向同一后端 |
| 专业版 | `https://pro.yuketang.cn` | 不同部署，字段名有差异 |
| 雨课堂 | `https://www.yuketang.cn` | 主站 |

App 的 `serverUrl` 在客户端里可切换，实测长江实例写入的是 `changjiang.yuketang.cn`。

---

## 2. 两套凭证：`sessionid` 与 `sid`

这是整个协议最关键的一点，也是很多人卡在 `50000 UNAUTHENTICATED` 的原因。

| cookie | 来源 | 能做什么 |
|---|---|---|
| `sessionid` | Web 扫码登录（`/pc/web_login`） | 课程、课次、开课检测等 `/v2/*`、`/v/*`、`/api/v3/classroom/*` |
| **`sid`** | **官方 App 登录** | **`/api/v3/lesson/*` 整族（签到、课件、弹幕、答题）** |
| `csrftoken` | 任一页面响应 `Set-Cookie` | POST 请求的 CSRF 校验 |
| `django_language` | 同上 | 语言 |

### 2.1 判定实验（同一 lesson，只换 cookie）

```
cookie "sessionid=X"          -> {"code":50000,"msg":"UNAUTHENTICATED"}
cookie "sessionid=X; sid=Y"   -> {"code":0, ...}
```

结论：

- `sid` 是 v3 lesson 族的**实际凭证**
- **`sid` 与 `sessionid` 不绑定**：Web 扫码得到的 `sessionid` 配 App 的 `sid` 同样能通
- 只带 `sid` 不带 `sessionid` 也能通（`sid` 单独即可）

### 2.2 网关层还有一道门：`X-Client`

同一个 `sessionid`，只改一个头：

```
X-Client: web      -> HTTP 401，无 Content-Type，
                      x-envoy-decorator-operation: cube-api-gateway...
X-Client: android  -> HTTP 401
X-Client: ios      -> HTTP 401
X-Client: app      -> HTTP 200，application/json，进入业务层
```

所以请求 `/api/v3/lesson/*` 必须同时满足：`X-Client: app` + `sid`。

---

## 3. 官方 App 的请求形态（抓包实录）

```
user-agent: Android
x-client: app
xtua: client=app&tag=1.3.5&platform=Android
version: 1.3.5
brand: <机型>            systemversion: <安卓版本>
buildnumber: 1800        incremental: <构建号>
isphysicaldevice: true
xtbz: ykt
x-uid: <userId>
cookie: sessionid=<…>; sid=<…>; csrftoken=<…>; django_language=zh-cn
accept: application/json
content-type: application/json      （POST 时）
```

实测要点：

- **没有任何 `Authorization` 头**，纯 cookie 鉴权
- **没有请求签名**：`X-Sign` / `X-Timestamp` / `X-Nonce` / `appSecret` / `HmacSHA256` 在官方包里
  出现次数均为 0
- `xtua` 等设备头对业务判定似乎不起作用（削减实验里删掉也能通），但建议照抄
- 用带 cookie jar 的会话复用请求头可能失败，关键接口要一次干净的独立请求

---

## 4. Web 扫码登录（WebSocket）

```
wss://changjiang.yuketang.cn/wsapp/
  → send {"op":"requestlogin","role":"web","version":1.4,"type":"qrcode","from":"web"}
  ← {"op":"requestlogin","loginid":"<uuid>","expire_seconds":60,
     "ticket":"https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket=...",
     "qrcode":"http://weixin.qq.com/q/02I3...","isReply":true}
  ← {… "subscribe_status":…, "UserID":…, "Auth":… }      # 扫码确认后
GET  /v/course_meta/user_info                            # 顺带下发 csrftoken
POST /pc/web_login  {"UserID":…, "Auth":…}               # → Set-Cookie: sessionid
```

三个坑：

1. **`UserID`/`Auth` 在 `subscribe_status` 那帧里**，不在首帧。只读首帧会得到「扫码成功但登录失败」
2. `qrcode` 字段是 `http://weixin.qq.com/q/...` 短链，直接编码成二维码即可；`ticket` 是微信官方图片地址
3. 二维码 `expire_seconds` 实测 **60 秒**，过期必须重新 `requestlogin`

`sid` **不会**由这条链路下发。

---

## 5. App 登录：`sid` 的唯一来源

```
POST /api/v3/user/login/app
Content-Type: application/json
x-client: app

{"type":3,
 "phoneNumber":"<手机号>",
 "email":"",
 "code":"<6 位短信验证码>",
 "pushDeviceId":"<19 位十六进制设备号>",
 "ticket":"","rand":""}
```

成功返回：

```json
{"code":0,"msg":"","data":{"id":"<userId>","avatar":"...","name":"...",
                           "school":"...","schoolNumber":"..."}}
```

**`sid` 不在这份 JSON 里，而在响应的 `Set-Cookie` 中。**

### 5.1 图形验证码的门禁差异（重要）

```
POST /api/v3/user/login/app   {code:"000000", ticket:"", rand:""}  -> 50046 验证码错误
POST /api/v3/user/code/send   {ticket:"", rand:""}                 -> 50046 验证码错误
```

- **登录接口不校验 `ticket`**：它抱怨的是短信码
- **发码接口校验 `ticket`**：空值直接拒

所以可以合法地做到「短信由官方前端发（图形码由它解决）+ 登录与取 `sid` 脚本化」。

### 5.2 短信发码（需要图形码）

```
POST /api/v3/user/code/send
{"phoneNumber":"<手机号>","email":"","ticket":"<图形验证码令牌>","rand":"<随机串>"}
```

`ticket` 形如 `tr03…`（较长），`rand` 形如 `@9Af`，来自平台图形验证码组件。
本仓库未实现图形码求解，也不建议实现。

### 5.3 `sid` 的存活时间

实测约 **2 小时**：15:17 登录 → 17:09 仍可用 → 17:25 失效（50000）。
它是会话级凭证，**不是一次性配置就能长期用的东西**。

---

## 6. 签到：进班与考勤是同一个请求

```
POST /api/v3/lesson/checkin
x-client: app
Content-Type: application/json
Cookie: sessionid=<任意有效会话>; sid=<App 的 sid>

{"source":23, "lessonId":"<lessonId 字符串>", "joinIfNotIn":true}
```

成功返回：

```json
{"code":0,"msg":"OK","data":{
  "role":5,
  "lessonId":"<…>",
  "lessonToken":"eyJ0eXAiOiJKV1Qi…",
  "identityId":"<…>",
  "identityName":"<姓名>",
  "identityNumber":"<学号>"}}
```

关键语义：

- **`joinIfNotIn: true`** = 不在班就直接进班。所以这一次调用同时完成
  「进班」与「签到」，**不需要另外调任何进班接口**
- **不需要 5 位课堂暗号**，也不需要扫码拿 `sign`

### 6.1 两个必踩的坑

| 坑 | 实际后果 |
|---|---|
| `lessonId` 传**数字** | `{"code":50400,"msg":"BAD_REQUEST"}` —— 必须是字符串 |
| 请求带 `Authorization` 头 | 同样 `50400` —— 必须与官方 App 一致的干净请求头 |

### 6.2 `lessonToken`

服务端签发的 JWT（HS256），payload：

```json
{"lessonId":"…","userId":"…","identityId":"…","iat":…,"exp":…}
```

有效期 **6 小时**（`exp - iat = 21600`）。后续课件、弹幕、答题都用它。
**无法伪造**——HS256 的密钥在服务端。

### 6.3 带暗号的网页端路径（仍然有效，但已非首选）

PC 网页端 bundle 里的 `joinClass` 逻辑：

```js
if (5 !== code.length) return 走 join_classroom;   // 不是 5 位 → 班级邀请码
if (/[0-9]/.test(code.charAt(0))) return checkin(14, code);   // 首位数字 → 新接口
r = { invite_code: code, source: 14 };             // 否则 → 旧接口
```

| 条件 | 端点 | body |
|---|---|---|
| 5 位且首位是数字 | `POST /api/v3/lesson/notkn/checkin` | `{source:14, inviteCode:码}` |
| 5 位且首位非数字 | `POST /api/lesson/web_check_in` | `{invite_code:码, source:14}` + `X-CSRFToken` |

注意：`notkn/checkin` 在官方 App 的 214 条路径里**不存在**，它是网页端专用。

---

## 7. 端点清单

### 7.1 可用

| 端点 | 方法 | 凭证 | 说明 |
|---|---|---|---|
| `/api/v3/classroom/on-lesson-upcoming-exam` | GET | sessionid | **开课检测的数据源**，读 `data.onLessonClassrooms` |
| `/v2/api/web/courses/list?identity=2` | GET | sessionid | 课程列表 |
| `/v2/api/web/classroom_archive` | GET | sessionid | 归档课程 |
| `/v2/api/web/logs/learn/{cid}?actype=-1&page=0&offset=500&sort=-1` | GET | sessionid | 课次列表（**`offset` 实际是 PageSize**） |
| `/api/v3/user/basic-info` | GET | sessionid | 判活 |
| `/v/course_meta/user_info` | GET | sessionid | 用户信息，顺带下发 `csrftoken` |
| `/api/v3/classroom/basic-info?classroom_id=` | GET | sessionid | 班级信息 |
| **`/api/v3/lesson/checkin`** | POST | **sid** | **进班+签到**，见第 6 节 |
| `/api/v3/lesson/basic-info` | GET | sid | 课堂信息（教师、开始时间等） |
| `/api/v3/lesson/ai-task/receive-list` | GET | sid | AI 任务 |
| `/api/v3/message/notice-list/` | GET | sessionid | 通知 |
| `/mobile-app/api/app-version/app-latest/` | GET | 无 | 版本检查 |

### 7.2 不可用 / 易误判

| 端点 | 现象 | 真相 |
|---|---|---|
| `/api/v3/lesson-summary/student` | `code:0` 但 `data.errorCode:-1` | **课后学习报告**接口，不是进班入口；官方 App 里出现 0 次 |
| `/api/v3/lesson-summary/checkin` | Envoy 直接拒，403/500 随形状跳变 | 路由不可用 |
| `/v/course_meta/on_lesson_courses` | 永远返回空数组 | 看着成功，实际是空的，只能兜底 |
| `/api/v3/user/login/app/wechat` | HTTP 500 | 无法作为入口 |

---

## 8. 错误码

| code | msg | 含义 |
|---|---|---|
| 0 | OK | 成功（**但 lesson-summary 族要看 `data.errorCode`**） |
| 50000 | UNAUTHENTICATED | 缺 `sid`（或 `sid` 过期） |
| 50002 | LESSON_UNAUTHORIZED | 缺课堂上下文——通常是没签到成功就调了需要上下文的接口 |
| 50400 | BAD_REQUEST | 参数形状不对（`lessonId` 传了数字、带了 `Authorization`） |
| 50046 | 验证码错误 | 短信码错/过期，或发码缺图形码 `ticket` |
| 50011 | — | 手机号未注册 |

**最阴的一条**：`lesson-summary` 族拒绝时顶层 `code` 仍是 `0`，真实结论在 `data.errorCode`。
只看顶层 `code` 会把失败当成功。

---

## 9. 开课检测的字段来源

数据源不是 `/v/course_meta/on_lesson_courses`。取自 PC bundle 的解析逻辑：

```js
e = API.pc.index.on_lesson_upcoming_exam
if ((n = await get(e)).code === 0) {
  l = n.data.onLessonClassrooms ?? []       // 正在上课的课堂
  u = n.data.upcomingExam ?? []
  lessonList = l.map(x => Object.assign(x, { id: x.lessonId, isV3: true }))
}
```

条目字段：`courseName`、`classroomName`、`lessonId`、`classroomId`、`courseId`、
`role`（1/2 教师侧，其余学生）、`openTeacher`。

字段名在不同部署下不一致，做兼容时至少兜 `lesson_id / courseware_id / id` 三套命名。

---

## 10. 想自己抓一次包时

Flutter 的 `dart:io` **不读 Android 系统代理**，普通 CONNECT 代理抓不到它的流量。
可行路径：

1. 模拟器 `adb root`
2. `openssl` 自签 CA + 目标域名证书
3. `mount --bind` 覆盖 `/system/etc/security/cacerts`
   （Android 15 无法 remount `/system`，但 bind mount 可行）
4. `adb reverse tcp:8081 tcp:8081`
5. `iptables -t nat -A OUTPUT -p tcp -d <yuketang IP> --dport 443 -j REDIRECT --to-ports 8081`
6. 本机跑一个只转发该域名的 TLS 终结代理
7. 在 App 里操作几下，从日志的 `cookie:` 行取 `sid=`

清理：`iptables -t nat -F OUTPUT`、`umount`、`adb reverse --remove-all`。

---

## 11. 未解决的问题

- `sid` 的准确有效期与续期机制（只观察到约 2 小时）
- `sid` 是否与设备指纹（`libtmsqmp.so` / `libtpcore-master.so`）绑定
- `lesson-summary` 族 `errorCode:-1` 的确切含义
- 图形验证码 `ticket` 的签发接口（本仓库不打算实现求解）

---

## 12. 复现建议

如果你要自己写一份，最小可用路径是：

1. `GET /v/course_meta/user_info` + `POST /pc/web_login` 拿到 `sessionid`
2. 用手机号 + 短信码调 `POST /api/v3/user/login/app`，从 `Set-Cookie` 取 `sid`
3. `GET /api/v3/classroom/on-lesson-upcoming-exam` 看哪节课在上
4. `POST /api/v3/lesson/checkin` `{source:23, lessonId:"<串>", joinIfNotIn:true}`

四步之外都是锦上添花。注意第 6 节的三个坑，否则会反复收到 `50400` / `50000`。
