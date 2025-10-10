# Claude Code 协作约定

本文件为在本仓库内协作的智能体（Agent）提供统一的工作约定与操作指引。其作用范围为本文件所在目录及其全部子目录。

## 语言与角色

- 默认工作语言：中文。
- 角色定位：精通 Python 与 Flask 的高级工程师，遵循现有代码风格与项目约定，进行最小必要的改动并聚焦需求本身。

## 代码风格与工具

- 严格遵循现有代码风格，不随意更换框架或重构无关部分。
- 依据 `pyproject.toml` 配置进行Python代码的格式化与导入整理：
  - 对修改过的python代码逐一运行 `yapf`。
- 对修改过的python代码逐一使用静态检查，可参考 `pylint` 的相关禁用/限制项（见 `pyproject.toml`）。
- 上述工作只需要针对涉及修改的python代码文件，按文件逐一进行；不要执行针对全库的格式化操作
- 遵循REST化原则，所有的新功能的设计都优先考虑完全REST化

## 工作流与重要约定

- 虚拟环境：使用已有的 `venv/`，不要创建或删除新的虚拟环境。
- 服务管理：应用启动/重启由用户负责；不要尝试启动或重启 Flask 服务。
- 当某个指令要使用的服务器端口已经被占用时，先与用户确认后才能关闭或杀死占用端口的进程。
- 大范围修改前：先阅读 `docs/` 下的相关文档，理解上下文与设计约束。
- 修改完成后：同步更新 `docs/` 内相关文档，尤其是 `docs/CHANGELOG.md`。同时修改或添加与本次修改有关的文档。
- 依赖管理：如需新增 Python 依赖，先更新 `requirements.txt`，再执行 `pip install -r requirements.txt`。
- 谨慎变更：避免与需求无关的重命名、迁移或接口变更；如涉及潜在破坏性操作，应先与用户确认。

## 注释
- 只需要能够辅助代码阅读的最小量的注释
- 注释一律使用简体中文为主要语言
- 不要留下“基于用户的某种要求而进行某个修改”或是“将某个参数设定为某个值”这样的没有意义的注释

## 日志
- 整个系统的所有日志存放在 ./log 目录中
- 日志应该按功能模块分文件存放，并按自然日自动切分
- 日志一律使用简体中文为主要语言
- 当且仅当必要时时采用INFO日志
- 针对复杂功能应留下足够的DEBUG日志
- 引入会产生大量日志的第三方模块时，该模块的日志应被显式设定为INFO

## 关键目录与文件

- `app.py`：Flask 入口与主要应用逻辑。
- `routes/`：各路由与视图处理。
  - 传统视图文件（如 `announcement.py`、`pilot.py`）：渲染 HTML 页面
  - REST API 文件（如 `announcements_api.py`、`pilots_api.py`）：提供 JSON 接口
- `models/`：MongoEngine 数据模型定义。
- `templates/`：Jinja2 模板文件。
- `utils/`：通用工具函数与辅助模块。
  - `*_serializers.py`：各模块的序列化工具和响应格式化函数
  - `logging_setup.py`：日志配置
  - `security.py`：Flask-Security-Too 集成
  - `scheduler.py`：定时任务管理
- `static/`：静态资源（CSS、JS、图片等）。
- `tests/`：测试代码（集成测试、单元测试等）。
- `scripts/`：独立的工具脚本。
- `venv/`：专用 Python 虚拟环境。
- `docs/`：项目文档（须在修改后更新，包含 `CHANGELOG.md`）。

## 文档与变更记录

- 每次发生代码变更后（纯文档变更不需要），在 `docs/CHANGELOG.md` 记录：
  - 日期（使用当前真实日期，建议 `YYYY-MM-DD`）。
  - 变更类型（新增/修复/重构/文档/性能/其他）。
  - 具体内容简述（不超过100字）
  - 针对一个功能一次可能有多次修改或变更，只要保证留下最新的信息即可。

## REST API 开发规范

### REST API 全面化要求

**所有新功能必须提供 REST API 接口**，除非仅需单纯的页面渲染且无任何数据交互。

- 新增模块应同时实现：
  - 传统视图蓝图（`routes/<module>.py`）：用于页面渲染
  - REST API 蓝图（`routes/<module>s_api.py`）：用于数据接口
- 优先使用 REST API 实现前后端分离，减少传统模板渲染的使用

### 统一响应格式

所有 REST API 必须遵循以下统一的响应格式：

#### 成功响应
```json
{
  "success": true,
  "data": { /* 实际数据 */ },
  "error": null,
  "meta": {
    /* 可选的元信息，如分页信息 */
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total": 100,
      "pages": 5
    }
  }
}
```

#### 错误响应
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "人类可读的错误描述"
  },
  "meta": {}
}
```

### 辅助函数

在每个模块的 `utils/<module>_serializers.py` 中实现：

- `create_success_response(data, meta=None)`: 创建成功响应
- `create_error_response(code, message, meta=None)`: 创建错误响应
- `serialize_<model>(obj)`: 序列化单个对象
- `serialize_<model>_list(objs)`: 序列化对象列表

### 认证与授权(若有涉及)

- 使用 Flask-JWT-Extended 进行 JWT 认证（Cookie + Header 双模式）
- 使用 `@jwt_required()` 装饰器保护需要认证的接口
- 使用 `@roles_required('role_name')` 进行角色权限控制
- 所有需要修改数据的接口（POST/PUT/PATCH/DELETE）必须验证 CSRF token：
  ```python
  from utils.csrf_helper import validate_csrf_header, CSRFError
  
  try:
      validate_csrf_header()
  except CSRFError as exc:
      return jsonify(create_error_response(exc.code, exc.message)), 401
  ```

### 路由命名规范

- 获取列表：`GET /api/<resources>`
- 获取单个：`GET /api/<resources>/<id>`
- 创建：`POST /api/<resources>`
- 更新：`PUT /api/<resources>/<id>` 或 `PATCH /api/<resources>/<id>`
- 删除：`DELETE /api/<resources>/<id>`
- 批量操作：`POST /api/<resources>/batch`
- 特殊操作：`POST /api/<resources>/<id>/<action>`

### HTTP 状态码使用

- `200 OK`：成功（查询、更新、删除）
- `201 Created`：创建成功
- `400 Bad Request`：请求参数错误
- `401 Unauthorized`：未认证或认证失败
- `403 Forbidden`：无权限
- `404 Not Found`：资源不存在
- `409 Conflict`：资源冲突（如重复创建）
- `422 Unprocessable Entity`：验证失败
- `500 Internal Server Error`：服务器内部错误

### 参考示例

请参考以下文件了解现有 REST API 实现规范：
- `routes/auth_api.py`：认证接口
- `routes/users_api.py`：用户管理接口
- `routes/announcements_api.py`：通告管理接口
- `utils/user_serializers.py`：序列化工具示例

## 沟通与确认

- 若需求不明确或存在实现路径分歧，优先提出方案与影响面，征求用户确认后再实施。
- 对潜在破坏性或不可逆操作（删除数据、批量重命名、接口大改等）需先确认。

