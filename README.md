# UnifiedMessagesManagement

统一消息管理（智能应用创新开发大赛初赛项目）。

## 目录结构

```
UnifiedMessagesManagement/
├── docs/                          # 比赛设计文档、需求分析等赛事资料
└── demo/                          # 演示模块
    └── 统一消息管理_初赛提交/      # 初赛提交版本（2026-11-17 final）
        ├── app.py                 # 应用入口
        ├── config.py              # 配置
        ├── adapters/              # 钉钉 / 飞书等消息平台适配器
        ├── core/                  # 消息总线、状态机、存储等核心逻辑
        ├── web/                   # Web 界面（templates + static）
        ├── tests/                 # 单元测试
        ├── docs/                  # 架构、接入指南、验证记录
        ├── Dockerfile             # 容器化部署
        └── docker-compose.yml
```

## 快速开始

```bash
cd demo/统一消息管理_初赛提交
pip install -r requirements.txt
python app.py
```

详见 `demo/统一消息管理_初赛提交/README.md`。
