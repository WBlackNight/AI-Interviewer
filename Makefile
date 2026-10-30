.PHONY: infra infra-down backend frontend test ui ui-check status preview package

# 启动基础设施（PostgreSQL + Redis + Qdrant）
infra:
	docker compose up -d

infra-down:
	docker compose down

# 后端开发服务（默认启发式模式，无需任何 API Key）
backend:
	cd backend && uvicorn app.main:app --reload --port 8000

# 前端开发服务
frontend:
	cd frontend && npm run dev

# 运行后端测试
test:
	cd backend && python -m pytest -q

# Native UI: maintain ui/, deliver root HTML and assets/.
ui:
	python tools/project.py build

ui-check:
	python tools/project.py check

status:
	python tools/project.py status

# 可通过ARGS显式传入--voice-provider doubao --local-mail。
preview:
	python tools/project.py preview $(ARGS)

package:
	python tools/project.py package
