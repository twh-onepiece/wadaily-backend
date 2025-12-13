.PHONY: help install dev up down build logs shell test clean

help: ## ヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Poetry関連
install: ## Poetry依存関係をインストール
	poetry install

update: ## Poetry依存関係を更新
	poetry update

shell: ## Poetry仮想環境に入る
	poetry shell

# Docker関連
up: ## Dockerコンテナをビルドして起動
	docker compose up --build

up-d: ## Dockerコンテナをバックグラウンドで起動
	docker compose up -d --build

down: ## Dockerコンテナを停止して削除
	docker compose down

build: ## Dockerイメージをビルド
	docker compose build

logs: ## Dockerコンテナのログを表示
	docker compose logs -f api

restart: ## Dockerコンテナを再起動
	docker compose restart

exec: ## Dockerコンテナに入る
	docker compose exec api bash

# テスト関連
test: ## テストを実行
	poetry run pytest

test-v: ## テストを詳細表示で実行
	poetry run pytest -v

# クリーンアップ
clean: ## キャッシュファイルを削除
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

clean-all: clean down ## 全てのクリーンアップ(Docker含む)
	docker compose down -v
