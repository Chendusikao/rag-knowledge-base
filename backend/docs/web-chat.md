# 用户前端与后端调试入口

项目只保留一套正式用户界面，避免用户功能与开发调试混在一起。

## 用户入口

启动前后端后，打开：

```
http://localhost:3000/
```

用户前端提供首次企业初始化、登录、部门知识库、资料导入、知识问答、用户权限和审计安全页面。不同角色只显示与自身职责匹配的导航。

## 开发调试入口

后端运行在 `http://127.0.0.1:8000`，根路径会跳转到 Swagger：

```
http://127.0.0.1:8000/docs
```

检索参数、评测、Provider、任务状态和其他内部接口通过 Swagger、脚本或日志调试，
不出现在普通用户前端导航中。

## 关键接口

- `GET /health`：健康状态
- `GET /api/v1/auth/status`：初始化与登录状态
- `/api/v1/departments`、`/api/v1/users`：部门和用户管理
- `/api/v1/knowledge-bases/{kb_id}/permissions`：知识库单独授权
- `GET /api/v1/audit-events`：只追加审计记录
- `GET /api/v1/security/status`：数据安全部署状态
- `GET /api/v1/meta`：当前模型与解析配置
- `POST /api/v1/chat/stream`：流式问答
- `GET /api/v1/retrieval/inspect`：检索调试
- `/api/v1/evaluation-*`：评测任务
- `/api/v1/provider-profiles*`：Provider 配置与连接测试

## 改动后如何生效

后端代码修改后重启：

```
cd E:\xaizai\wendaxitog\backend
.\scripts\start_backend.ps1
```

前端代码修改后由 Next.js 开发服务器自动更新；生产构建可运行 `npm run build`。
