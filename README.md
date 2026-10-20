# 雨课堂协议研究

对**长江雨课堂**（`changjiang.yuketang.cn`）公开客户端与后端之间协议的独立研究，
附带一个用来验证结论的客户端（Windows GUI + Android）。

所有结论来自**静态提取 + 真机抓包 + 真实课堂实测**，不依赖任何私有资料。

<br>

**核心发现**：雨课堂 v3 接口的凭证不是 `sessionid`，而是 **`sid` cookie**。
拿到它之后，官方 App 的签到接口一次调用即可**进班 + 签到**，不需要 5 位课堂暗号、不需要扫码。

<br>

| | |
|---|---|
| 🟢 **实测可用** | 扫码登录 · 课程与课次 · 开课检测 · **免暗号签到（App 接口）** |
| 🔴 **未实现** | 改成绩 · 代答 · 超时补答 · 操作他人账号 |
| ⚠️ **前置条件** | 签到需要官方 App 的 `sid`，见 [如何拿到 sid](#如何拿到-sid) |

---

## 它能做什么

| 能做 | 不能做 |
|---|---|
| 免扫码进入**你自己已选课**的课堂 | 进入你没选的课 |
| **不需要签到码**完成签到 | 替别人签到、操作他人账号 |
| 读取你自己账号的课程、课次、课件 | 读取别人的数据 |
| 检测开课状态、一次签完所有在上的课 | 改成绩、代答、看别人答案 |

---

## 截图

![客户端界面](preview.png)

<details>
<summary>登录界面</summary>

![登录界面](preview_login.png)

</details>

---

## 快速开始

### 方式一：Windows 客户端（推荐）

```bash
pip install -r requirements.txt
pip install pyinstaller
python build.py --onefile      # 产物：dist/YuketangClient.exe（单文件，免安装）
python app_gui.py              # 或者不打包，直接跑
```

> exe 有 54 MB，**没有放进仓库**（`.gitignore` 排除）。仓库里只放体积小的 Android APK。
> 打包脚本已排除 PySide6 的 WebEngine / QML / Multimedia 等无关模块，体积比默认小一半。

### 方式二：命令行

```bash
pip install -r requirements.txt

python ykt.py login                 # 微信扫码，一次即可，登录态落盘
python ykt.py live                  # 看哪节课正在上
python ykt.py checkin --live        # 一次签完所有正在上的课
python ykt.py watch --observe       # 【推荐】只检测开课，不动手
```

仓库根目录另有 `一键签到.bat`，双击等价于 `checkin --live`。

### 方式三：Android

`dist/YuketangStudy-0.4.0-debug.apk`（debug 签名，直接安装）。

**这不是桌面版打包过来的**——PySide6 没有 Android 目标，是独立重写的一份：
纯 Java + 原生 Views + `HttpURLConnection`，零第三方依赖。详见 [android/README.md](android/README.md)。

主界面功能：sid 输入框 · **App 登录换 sid** · 签到码 · 自动进班 · 自动签到 · 运行日志。

```bash
cd android
export JAVA_HOME=/path/to/jdk-17      # compileSdk 34
export ANDROID_HOME=/path/to/android-sdk
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

> Android 版**能编译、包结构已校验（aapt2 + apksigner）**，界面与签到流程在模拟器上验证过；
> 国产 ROM 的后台存活仍需自行确认。

---

## 核心：签到是怎么通的

### 一句话

`sid` 是 v3 接口认的凭证，`joinIfNotIn` 让签到顺带完成进班。

### 凭证对照（同一 `lesson_id`，只换凭证）

```
cookie "sessionid=X"          -> 50000 UNAUTHENTICATED
cookie "sessionid=X; sid=Y"   -> 0
```

`sid` 由官方 App 登录时下发，Web 扫码登录拿不到，且**与 sessionid 不绑定**
（Web 的 `sessionid` 配 App 的 `sid` 同样能通）。

### 调用

```
POST /api/v3/lesson/checkin
body: {"source":23, "lessonId":"<字符串>", "joinIfNotIn":true}
cookie: sessionid=<任意有效会话>; sid=<App 的 sid>
```

返回 `data.lessonToken`（JWT，含 `lessonId/userId/identityId`，有效期 6 小时），
后续课件、弹幕、答题都用它。

### 两个必须记住的坑

| 坑 | 后果 |
|---|---|
| `lessonId` 传**数字** | `50400 BAD_REQUEST`，必须字符串 |
| 请求带 `Authorization` 头 | 同样 `50400`，必须与官方 App 一致的干净请求头 |

---

## 如何拿到 sid

`sid` 只能来自**官方 App 的登录**，Web 扫码拿不到。三种方式，从简单到复杂：

### 方式一：在客户端里登录（推荐，最简单）

**Windows**：点右上角 **「App 凭证」** → 填手机号 + 短信验证码 → 点「登录并获取 sid」

**Android**：主界面点 **「App 登录（手机号 + 短信码）换 sid」** → 填手机号 + 验证码

**命令行**：

```bash
python ykt.py app-login --phone 13800000000
# 提示输入 6 位短信验证码
```

短信要**你自己发**：打开官方 App 登录页 → 输手机号 → 点「获取验证码」。

> 为什么不能代发：`POST /api/v3/user/code/send` 要图形验证码 `ticket`，
> 但 `POST /api/v3/user/login/app` **不要**——所以图形码交给你在官方 App 里点，
> 剩下的登录与 sid 提取全自动。

> **注意：`sid` 是会话凭证，会过期。** 本次实测约 **2 小时**后失效
> （15:17 登录 → 17:25 失效），不是一次性配置就能永久用的东西。
> 好在过期后重走一遍「方式一」只要几十秒。

拿到后自动写入 `session.json`（桌面端会同时写根目录与 `dist/`）。

### 方式二：直接粘贴 sid

已经有 sid（比如从别处抓到的）就跳过登录：

```bash
python ykt.py app-import --sid <那串值>
```

GUI 里「App 凭证」对话框下半部分也能直接粘；Android 上就是主界面的输入框。

### 方式三：抓包（最后手段）

客户端登录路走不通时，可以自己抓官方 App 的流量取 `sid=`。

Flutter 不读系统代理，CONNECT 代理抓不到，必须透明重定向：

1. 模拟器 `adb root`
2. `openssl` 自签 CA + 目标域名证书
3. `mount --bind` 覆盖 `/system/etc/security/cacerts`
4. `adb reverse tcp:8081 tcp:8081`
5. `iptables -t nat -A OUTPUT -p tcp -d <yuketang IP> --dport 443 -j REDIRECT --to-ports 8081`
6. 本机跑只转发该域名的 TLS 终结代理
7. 在 App 里点几下，从日志的 `cookie:` 行取 `sid=`

拿到后 `python ykt.py app-import --from-capture path/to/capture.log`。
完整步骤与踩坑见 [docs/FINDINGS.md](docs/FINDINGS.md) 第二节。

### sid 失效了

```
[!] App 的 sid 已失效（登录态过期）
    最快的恢复方式（手机号 + 短信码，不用抓包）：
        python ykt.py app-login --phone <你的手机号>
```

GUI 点「App 凭证」，Android 点「App 登录」，效果相同。**不需要重新搭抓包环境。**

如果你习惯把 `sid` 存在别处备份，也可以直接 `app-import --sid <值>` 粘回去——
但过期了粘回去也没用，只能重新登录。

---

## 项目结构

```
ykt.py                 协议后端 + CLI（GUI 直接 import 它）
app_gui.py             PySide6 图形界面
build.py               PyInstaller 打包
一键签到.bat            双击签完所有正在上的课
tools/secret_scan.py   提交前凭据自检（扫工作区 + 全部 git 历史）

android/               Android 工程（纯 Java，零依赖）
docs/FINDINGS.md       研究记录：证据、推翻过的假设、端点总表
SECURITY.md            凭据处理、能力边界、开源合法性评估
NOTICE.md              来源致谢 + 商标声明
GONGXIAOHU-ANALYSIS.md 第三方 App「工小湖」的机制与隐私提示
```

### session.json 在哪

| 运行方式 | 位置 |
|---|---|
| `python ykt.py …` | 仓库根目录 |
| `dist/YuketangClient.exe` | **exe 所在目录**（即 `dist/`） |

两处是**不同的文件**，所以 CLI 和 GUI 默认不共享会话。这也是「命令行能签、exe 说没有 sid」
的常见原因——用 `app-import` 导入会同时写两边。

---

## 常见问题

**Q：为什么 exe 说「没有 App 的 sid」，但命令行能签？**
两个 `session.json` 不是同一个文件。重新跑一次 `app-import`，它会同时写两边。

**Q：`live` 显示没有课，但网页上确实在上课？**
字段名在不同部署下不一致。跑 `python ykt.py live --raw` 看原始 JSON 对字段名。

**Q：签到失败提示 `UNAUTHENTICATED`？**
`sid` 过期。去官方 App 重新登录后重新导入。

**Q：老师开了大屏动态码，还能签吗？**
能。`sid` 这条路径不依赖二维码里的 `sign`。

**Q：为什么 `app-login` 还需要我自己发短信？**
发码接口 `POST /api/v3/user/code/send` 要图形验证码 `ticket`，脚本代过不了；
但登录接口 `POST /api/v3/user/login/app` **不要**。所以图形码交给官方 App，其余全自动。

**Q：`sid` 和 `sessionid` 有什么区别？**
`sessionid` 是网页端登录态，只能读课程、看开课；`sid` 是 App 侧凭证，
`/api/v3/lesson/*`（签到、课件、弹幕）只认它。两者不绑定，`sid` 配任意有效 `sessionid` 都能用。

**Q：会被发现吗？**
教师端能看到签到时间戳与来源。自动化签到的时间分布与人手不同，**不是不可发现的**。

---

## 已知限制

- **`sid` 是会话级凭证**：App 退出登录、改密码后失效，需要重新获取
- **开课检测字段名不固定**：`ykt.norm_lesson()` 兜了 `lesson_id/courseware_id/id` 等多套命名
- **轮询别拉满**：`/api/v3/*` 走统一网关，默认 5 秒足够
- **二维码 60 秒过期**：登录框会自动换码，正在扫的那张会失效
- **切换后端后需重新登录**：cookie 绑域名

---

## 安全与合规

请先读 **[SECURITY.md](SECURITY.md)**，其中包含：

- 凭据怎么存的（**明文，不假装加密**）以及为什么
- 本仓库**不含任何真实凭据或个人数据**（`tools/secret_scan.py` 可复核，扫描含全部 git 历史）
- **开源合法性评估**：著作权 / 反不正当竞争法第 12 条 / 刑法 285·286 / 个人信息保护法 / 平台规则，逐条给风险等级

三条底线：

1. **只操作你自己的账号**，只进入你自己已选课的课堂
2. **默认用观察模式**：`python ykt.py watch --observe`
3. **人不在课堂时不要开自动签到**——那是伪造出勤，违反课堂纪律，后果由使用者承担

本项目与北京慕华信息科技有限公司**无任何隶属或授权关系**。使用可能违反雨课堂用户协议。
代码按 MIT 协议「原样」提供，不附带任何担保。

> ⚠️ 分发时**只拿 exe 和 apk 两个文件**，不要打包整个 `dist/` —— 里面可能有你的 `session.json`。

---

## 致谢

协议认知建立在以下公开资料之上，详见 [NOTICE.md](NOTICE.md)：

- **[《工小湖：给雨课堂与学校教务做了个小程序》](https://blog.jiclub.site/2026/yuketang-deep-dive)** by Cталин — 提供了「`sign` 只约束旁听生」的关键判断
- **[RainClassSDK](https://github.com/Auto-CQUPT-Plan/RainClassSDK)** by Auto-CQUPT-Plan — 接口清单与鉴权头约定
- **[rainclassroom-scrapper](https://gitbucket.skyw.top/physicsdolphin/rainclassroom-scrapper)** by physicsdolphin — **WebSocket 扫码登录的具体实现**，没有这份参考本项目登录部分无从下手
- **[Ajax 的雨课堂爬虫笔记](https://aajax.top/2025/01/10/YuketangScrapper/)** — 课程/课次接口与 `offset` 实为 PageSize 的坑

### 关于「工小湖」这个 App

本项目对它做过静态分析，结论在 [GONGXIAOHU-ANALYSIS.md](GONGXIAOHU-ANALYSIS.md)。
一句话版本：它会把你雨课堂的**会话 cookie 发往作者自建服务器**，签到也由那台服务器代签。
它能自动签到，成立前提是**老师没开大屏动态码**——开了之后它同样签不上。

这不是漏洞指控，是数据流向的事实。

---

## 许可

[MIT](LICENSE) © 2026 SHUIZHILANLL

「雨课堂」「长江雨课堂」「学堂在线」及相关标识归北京慕华信息科技有限公司所有。
