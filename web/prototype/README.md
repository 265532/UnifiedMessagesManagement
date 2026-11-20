# UnifiedMessagesManagement 初赛 Web 原型

## 定调说明

面向多平台办公人员的工业实用型消息工作台。视觉以浅灰底、深海军蓝文字、单一青绿色关键动作和发丝边框为主；数字、状态和游标使用等宽字体，突出“每条消息可追踪、可回放”的工程感。

## 运行方式

直接用浏览器打开 `index.html`，或通过任意静态服务器访问。界面通过查询参数切换：

- `?screen=login`：登录
- `?screen=inbox`：消息工作台
- `?screen=conversation`：会话处理与回复
- `?screen=todos`：待办聚合
- `?screen=status`：状态回流
- `?screen=failure`：发送失败与恢复
- `?screen=offline`：断线补拉
- `?screen=unauthorized`：未认证拦截

## 设计边界

该原型用于 `02_原型设计` 的界面说明与截图，不代表真实产品已实现，也不能作为 `05_初步验证` 的真实运行证据。真实验证必须使用可运行产品与平台侧证据。