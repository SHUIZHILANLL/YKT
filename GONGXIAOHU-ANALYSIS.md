# 「工小湖」2.0.1 机制分析与隐私提示

> 本文是对第三方 App **工小湖 2.0.1** 的静态分析记录，结论用于说明它的实现方式，
> 以及一个用户应当知情的事实。分析对象不是我方代码。

## 分析对象

| 项 | 值 |
|---|---|
| 文件 | `工小湖2.0.1.apk` |
| 大小 | 15.27 MB（861 个归档条目） |
| SHA-256 | `63b2938f6998aafcad399f6f897c77638dc49ec7b7ee9fe172df06ce43d27272` |
| 框架 | uni-app（DCloud）+ Vue 3 |
| 关键产物 | `assets/apps/__UNI__A896164/www/app-service.js`（631,944 字节，未加密） |
| 运行时 | `assets/uni-jsframework-vue3.js`、`lib/*/libweexjss.so`、`lib/*/libweexcore.so` |

因为业务逻辑是编译进 `app-service.js` 的 JavaScript（非 DEX 字节码），
本次分析读的是**可读的 JS 源码级产物**，不是反编译推测。

**方法边界**：全程静态分析，未运行该 App、未登录、未发起任何真实请求。
下文所有结论都来自包内文件内容。

## 架构

```
工小湖 App ──→ https://hnit.jiclub.site ──→ changjiang.yuketang.cn
             （作者自建网关）                （雨课堂官方）
```

包内常量：

```js
API_BASE_URL  = "https://hnit.jiclub.site"
FOCUS_WS_URL  = "wss://hnit.jiclub.site/api/ws/lesson"
// 另有一套学校教务地址
jw.hnit.edu.cn
```

雨课堂后端可切换，内置四个：

```js
www       https://www.yuketang.cn
pro       https://pro.yuketang.cn
changjiang https://changjiang.yuketang.cn
huanghe   https://huanghe.yuketang.cn
```

**它不是一个纯客户端工具。** 关键功能都经过作者自建服务器。

## 登录：长轮询发生在网关一侧

```js
// 1) 优先直连官方拿登录 token
uni.request({ url: `${host}/api/v3/user/login/pre-info` })
//    → data.token / data.qrContent / data.qrImage

// 2) 直连失败则向网关要二维码
uni.request({ url: `https://hnit.jiclub.site/api/ykt/auth/qrcode` })

// 3) 长轮询——注意这个 URL 属于网关，不是雨课堂
uni.request({
  url: `${b}/api/ykt/auth/login-qr`,     // b = hnit.jiclub.site
  method: "POST",
  data: { token, server },
  timeout: 38000,
})
// code === 0     → 登录成功，响应里带 cookie
// code === 50002 → "等待扫码中"，继续轮询
```

这一点解释了一个常见的误判：雨课堂官方**没有** `/custom/auth/v1/auth/status`
这类长轮询端点，所以"长轮询登录"在某些分析里被判定为不存在。
准确的说法是：**PC 网页端走 WebSocket，而「工小湖」的长轮询是它自己服务器的**，两者并不矛盾。

关键含义：WeChat 扫码的确认过程由网关代为完成，**网关因此拿到并保存了用户的雨课堂会话 cookie**。

## 开课检测

```js
uni.request({
  url: `${host}/api/v3/classroom/on-lesson`,
  header: {
    Cookie: session.cookie,
    Referer: `${host}/lesson/fullscreen/v3/`,
  },
})
// 成功：data.data.onLessonClassrooms
// 失败或凭据失效：降级到网关
uni.request({ url: `https://hnit.jiclub.site/api/ykt/lesson/on-going?user_id=…&server=…` })
```

顺手纠正我方实现的一处：`/api/v3/classroom/on-lesson` 返回的容器字段**同样是
`onLessonClassrooms`**，并且这条路在对方 App 里是**主路径**（直连优先）。
我方目前主用 `/api/v3/classroom/on-lesson-upcoming-exam`，二者应该都能用，
但生产验证过的是前者。

## 签到：走网关，请求体里没有暗号

```js
uni.request({
  url: `https://hnit.jiclub.site/api/ykt/lesson/check-in`,
  method: "POST",
  data: {
    user_id, lesson_id, server,
    cookie: session.cookie,        // ← 用户的雨课堂 cookie 随请求发出
  },
})
```

响应处理：

```js
if (r.code === 0) {
  // ✅ 免扫动态码自动签到成功
  n.bypassDynamicCode = true;
  n.isCheckedIn = true;
} else if (r.code === 50070) {
  // ⚠️ 需现场动态码签到 —— 放弃
  n.requiresDynamicCode = true;
  n.isCheckedIn = false;
}
```

UI 文案与之一致：

> 任课教师开启了大屏动态码，请扫码或输入口令进班

## 结论：它没有绕过课堂暗号

这是本次分析最想澄清的一点。

| 情形 | 结果 |
|---|---|
| 老师**未开启**大屏动态码 | 网关可完成签到，App 显示「已自动签到」 |
| 老师**已开启**大屏动态码 | 网关返回 `50070`，App 显示「请扫码或输入口令进班」，**自身无法签到** |

佐证：整个 `app-service.js` 里 **「口令」只出现 1 次**，且只在那句提示文案中；
`uni.scanCode` 调用 **0 次**。也就是说它既没有暗号输入框，也没有扫码实现，
遇到动态码一律退回让用户自己走官方渠道。

所以那篇文章里「检测到开课广播就自动调接口完成打卡」成立的前提是：
**那节课本来就不需要暗号。** 这不是绕过，是这件事在没有动态码时本来就简单。

## 隐私提示（使用前应当知情）

三条事实，都来自包内代码：

1. **登录长轮询在网关侧完成**，因此网关取得用户的雨课堂会话 cookie。
2. **每次签到都把 `cookie` 放进请求体发给网关**。
3. 开课检测的**降级路径**同样由网关代查。

合并起来：网关持有会话，并能以用户身份操作其雨课堂账号。

App 引导页写的是：

> 会话数据仅在当前手机持久化

这句与上述代码行为不一致。本文只陈述差异，不推测动机。

**这不是漏洞指控，是数据流向的事实**。是否接受，由使用者自行判断。

## 与我方实现的差异（供参考）

| 能力 | 工小湖 | 本项目 |
|---|---|---|
| 登录 | 经第三方网关长轮询 | 直连官方（桌面 WebSocket / Android HTTP 轮询） |
| 会话存放 | 本地 + 网关 | 仅本地 `session.json` / SharedPreferences |
| 开课检测 | 直连 `on-lesson`，失败降级网关 | 直连官方，无第三方 |
| 无码签到 | 网关代签 | 直连官方，待定位具体端点 |
| 动态码签到 | 不支持，提示用户自理 | 支持（用户输入暗号） |
| 账号凭据外发 | 有 | 无 |

无码签到这个能力，本项目无法复制——原因在下面「技术路线对照」一节。

## 技术路线对照（关键）

把两边的实现摆在一起，就能看清为什么他能跑通、我们跑不通：

| | 工小湖 | 本项目 |
|---|---|---|
| 客户端是否调用雨课堂的进班接口 | **否，`lesson-summary/student` 在包内出现 0 次** | 是，直连该接口 |
| 课堂上下文来源 | 服务端在签到响应里返回 `bearer_token` / `lesson_token` / `presentation_list` | 尝试自己向雨课堂索取 |
| 逆向位置 | **服务端（不可见）** | 客户端（可见） |
| 结果 | 可用 | `50002 LESSON_UNAUTHORIZED` |

他的 `classroom.vue` 里进入课堂只有一个动作：

```js
const o = await ke(a.user_id, l.value, c.value);   // ke = 调他自己的服务器
if (0 === o.code && o.data) {
  T.value = s.bearer_token;            // 课堂 bearer
  // lesson_token / presentation_list / active_presentation_id
}
```

`ke()` 即 `/api/ykt/lesson/check-in`。**客户端从不向雨课堂索取课堂权限**，
全部由那台服务器代劳。

所以：**他的"实测可行"证明的是「那台服务器做得到」，不是「存在一条可复制的客户端路径」。**
本次对照最重要的结论是——**他客户端里没有可抄的进班实现。**

## 本项目侧的终局结论

真实课堂进行中实测：

- 进班候选 9 种变体（含 `&source=14`、`&sign=&ts=`、`&classroom_id`）→ 全部 `data.errorCode=-1`，
  且该接口本身是**课后学习报告**，不是进班入口
- 不计暗号的签到候选 5 种变体（`notkn/checkin` 与 `lesson/checkin`，带/不带 `Classroom-Id`）
  → 全部 `50002 LESSON_UNAUTHORIZED`

`LESSON_UNAUTHORIZED` 指缺课堂上下文，而课堂上下文是**签到成功后**才下发的。
于是形成闭环：**要进课堂得先签上，要签上得先有课堂上下文。**

唯一突破口是老师给的 5 位暗号，或扫大屏二维码取得 `sign`——正是本项目想避开的动作。


## 如何自行复核

```powershell
# 1) 解包
Expand-Archive 工小湖2.0.1.apk -DestinationPath apk_out   # 或任意 zip 工具

# 2) 业务逻辑在（未加密）
#    assets/apps/__UNI__A896164/www/app-service.js

# 3) 关键检索
Select-String -Path app-service.js -Pattern 'jiclub|login-qr|check-in|50070|requiresDynamicCode'
```

该文件是 uni-app 编译产物，变量名被压缩，但**字符串与协议字段完整保留**，
按上面的关键词即可定位到本文引用的每一段。

## 边界与声明

- 本文不含任何绕过、破解或未授权访问的方法。
- 分析对象为公开发布的安装包，不含逆向官方客户端私有代码。
- 未修改、未重打包、未分发该 App。
- 商标与著作权归各自权利人所有，详见 [NOTICE.md](NOTICE.md)。
