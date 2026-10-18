# 来源与致谢

本项目的协议认知来自以下公开资料的交叉验证。**没有任何一行代码是从这些项目直接复制的**，
但接口路径、字段名、登录链路的方向来自它们的启发。在此明确致谢。

---

## 1. 《工小湖：给雨课堂与学校教务做了个小程序》

- 作者：Cталин（StalinDev54）
- 原文：https://blog.jiclub.site/2026/yuketang-deep-dive
- 许可：CC BY-NC-SA 4.0

**提供了什么**：让我意识到「投屏二维码里的 `sign` 只是给旁听生用的旁路票据，在册学生凭 session
本来就有该 lesson 的访问权」这个关键判断，以及「官方前端倒计时归零不等于服务端关接口」的方向。

**本项目与之的差异**（详见 README 的对照表）：

- 该文的登录长轮询端点 `/custom/auth/v1/auth/status` 经实测在三个域名下均不存在；
  真实登录走 WebSocket（`wss://{host}/wsapp/`）。
- 该文的 `get_user_course_list`、`status == 1` 判断与实测接口不一致。
- 本项目未实现该文提到的「超时补答 / 重复提交覆盖」，只实现了进班与签到。

---

## 2. RainClassSDK

- 作者：Auto-CQUPT-Plan（重庆邮电大学）
- 仓库：https://github.com/Auto-CQUPT-Plan/RainClassSDK
- 许可：MIT

**提供了什么**：完整的 16 个接口清单与调用链，尤其是考试系统
（`changjiang-exam.yuketang.cn`）的 `gen_token → login → start_paper → show_paper → submit` 流程，
以及 `xtbz: ykt`、`X-CSRFToken` 这两个请求头约定。本项目的 `probe` 端点矩阵参考了它的结构。

---

## 3. rainclassroom-scrapper

- 作者：physicsdolphin / Ajax Dong
- 仓库：https://gitbucket.skyw.top/physicsdolphin/rainclassroom-scrapper
- 相关文章：https://aajax.top/2025/01/10/YuketangScrapper/

**提供了什么**：**WebSocket 扫码登录的具体实现**——`{"op":"requestlogin","role":"web","version":1.4,
"type":"qrcode","from":"web"}` 的请求体，以及 `pc/web_login` 用 `{UserID, Auth}` 换 `sessionid`
的关键一步。没有这份参考，本项目的登录部分无从下手。

同时该项目的 `courses/list?identity=2`、`classroom_archive`、
`logs/learn/{cid}?actype=-1&page=0&offset=500&sort=-1`（以及 `offset` 其实是 PageSize 这个坑）
也被本项目沿用。

---

## 4. 其他参考

- [heyblackC/yuketangHelper](https://github.com/heyblackC/yuketangHelper) — 雨课堂脚本仓库，早期接口形态参考
- [RainClassSDK 的 models 包](https://pkg.go.dev/github.com/Auto-CQUPT-Plan/RainClassSDK) — 响应结构参考

---

## 商标声明

「雨课堂」「长江雨课堂」「学堂在线」及相关标识归北京慕华信息科技有限公司所有。
本项目与上述公司**无任何隶属、合作或授权关系**，仅为个人对公开 Web 前端协议的独立研究。
