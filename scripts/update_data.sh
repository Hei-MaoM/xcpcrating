#!/usr/bin/env bash
#
# update_data.sh — 一键更新 xcpc-rating 数据源并重跑管线
#
# 解决的痛点：源数据原本默认从 /tmp/srk-collection/official 读取，而 /tmp 会被
# 系统定期清理，导致数据丢失。本脚本把源数据持久化到源码树之外的标准 cache 位置
# （$SRK_DATA_HOME，默认 ~/.cache/xcpc-rating/srk-collection），并通过符号链接
# /tmp/srk-collection 兼容所有硬编码 /tmp 路径的代码与 pytest。
#
# 流程：
#   1. 持久化 clone / pull 源数据仓库（algoux/srk-collection）
#   2. 建立 /tmp/srk-collection -> $SRK_DATA_HOME 兼容符号链接
#   3. 回放 + 回测（xcpc_rating.cli）          —— 可用 --no-backtest 跳过
#   4. 导出 web 数据（xcpc_rating.export_web）
#   5. 构建前端（npm run build）              —— 可用 --no-build 跳过
#   6. 打印摘要（数据 commit、contests/players 数、榜首选手）
#
# 用法：
#   bash scripts/update_data.sh [--no-build] [--no-backtest] [--data-home PATH]
#   bash scripts/update_data.sh -h | --help
#
set -euo pipefail

# ---------------------------------------------------------------------------- #
# 常量与路径（一切基于脚本自身位置解析，不依赖当前工作目录）
# ---------------------------------------------------------------------------- #
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPO_URL="https://github.com/algoux/srk-collection.git"
COMPAT_LINK="/tmp/srk-collection"
WEB_DATA_OUT="web/public/data"

# 源数据持久化位置：可被环境变量 SRK_DATA_HOME 或 --data-home 覆盖。
# 源数据现为本仓库的 git submodule（vendor/srk-collection）。默认指向它；仍可被
# 环境变量 SRK_DATA_HOME 或 --data-home 覆盖为任意外部 clone（走回退 clone/pull）。
DATA_HOME="${SRK_DATA_HOME:-$ROOT/vendor/srk-collection}"
SUBMODULE_PATH="$ROOT/vendor/srk-collection"

DO_BUILD=1
DO_BACKTEST=1

log() {
  echo "[update-data] $*"
}

die() {
  echo "[update-data] ERROR: $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
用法: bash scripts/update_data.sh [选项]

选项:
  --no-build         跳过前端构建（npm run build）
  --no-backtest      跳过回放+回测步骤（xcpc_rating.cli）
  --data-home PATH   覆盖源数据持久化目录（默认 ~/.cache/xcpc-rating/srk-collection，
                     或环境变量 SRK_DATA_HOME）
  -h, --help         显示本帮助并退出

行为:
  - 源数据持久化在 $SRK_DATA_HOME（默认 ~/.cache/xcpc-rating/srk-collection）。
  - /tmp/srk-collection 是指向上述目录的兼容符号链接（供硬编码 /tmp 的代码使用）。
  - 默认执行: clone/pull -> 回放回测 -> 导出 web 数据 -> 前端构建 -> 摘要。
EOF
}

# ---------------------------------------------------------------------------- #
# 解析参数
# ---------------------------------------------------------------------------- #
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build)
      DO_BUILD=0
      shift
      ;;
    --no-backtest)
      DO_BACKTEST=0
      shift
      ;;
    --data-home)
      [[ $# -ge 2 ]] || die "--data-home 需要一个路径参数"
      DATA_HOME="$2"
      shift 2
      ;;
    --data-home=*)
      DATA_HOME="${1#*=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "未知参数: $1（用 -h 查看帮助）"
      ;;
  esac
done

# 规范化为绝对路径（mkdir -p 后用 cd/pwd 解析，兼容 ~ 已由 shell 展开的情况）。
mkdir -p "$DATA_HOME"
DATA_HOME="$(cd "$DATA_HOME" && pwd)"
OFFICIAL_DIR="$DATA_HOME/official"

log "项目根:        $ROOT"
log "源数据目录:    $DATA_HOME"
log "official 路径: $OFFICIAL_DIR"
log "兼容符号链接:  $COMPAT_LINK"

# ---------------------------------------------------------------------------- #
# 1. 更新源数据（默认 submodule；自定义路径走 clone/pull 回退）
# ---------------------------------------------------------------------------- #
if [[ "$DATA_HOME" == "$SUBMODULE_PATH" ]]; then
  # 默认情形：vendor/srk-collection 是本仓库的 git submodule。submodule 的工作区
  # 里 .git 是一个指向 $ROOT/.git/modules/... 的文件（而非目录），所以不能用
  # `-d .git` 判断。用 submodule update --init --remote 一步搞定：未初始化则初始化，
  # 已初始化则拉取上游所跟踪分支的最新提交（--depth 1 保持浅克隆）。
  log "更新 submodule: git submodule update --init --remote --depth 1 -- vendor/srk-collection ..."
  if ! git -C "$ROOT" submodule update --init --remote --depth 1 -- vendor/srk-collection; then
    die "submodule 更新失败。请检查网络，或确认 .gitmodules 中 vendor/srk-collection
       的配置（git -C \"$ROOT\" submodule status）。"
  fi
elif [[ -e "$DATA_HOME/.git" ]]; then
  # 自定义的外部 clone（.git 可能是目录或 submodule 文件指针）。
  log "已存在仓库，执行 git pull --ff-only ..."
  if ! git -C "$DATA_HOME" pull --ff-only; then
    die "git pull --ff-only 失败。本地可能有偏离上游的提交或非快进历史。
       请手动检查 '$DATA_HOME'（git -C \"$DATA_HOME\" status），
       或删除该目录后重跑本脚本以重新 clone。"
  fi
else
  # 目录可能因 mkdir -p 已存在但为空；若非空且无 .git 则视为脏目录。
  if [[ -n "$(ls -A "$DATA_HOME" 2>/dev/null)" ]]; then
    die "'$DATA_HOME' 已存在且非空，但不是 git 仓库。
       请清空或删除该目录后重跑，以避免覆盖未知数据。"
  fi
  log "未发现仓库，执行 git clone --depth 1 ..."
  git clone --depth 1 "$REPO_URL" "$DATA_HOME" \
    || die "git clone 失败，请检查网络连接与仓库地址 $REPO_URL"
fi

[[ -d "$OFFICIAL_DIR" ]] || die "clone/pull 后未找到 official 目录: $OFFICIAL_DIR
       源仓库结构可能已变更，请检查 $DATA_HOME 的内容。"

# ---------------------------------------------------------------------------- #
# 1b. 叠加本仓库自带的 srk（上游没有的网络预选赛，见 srk-extra/）
#     上游 submodule 不含这些赛事，故每次更新后把 srk-extra/official 覆盖进去，
#     保证本地与 CI（pages.yml 同样的 cp 步骤）导出口径一致。
# ---------------------------------------------------------------------------- #
if [[ -d "$ROOT/srk-extra/official" ]]; then
  log "叠加自带 srk: cp -R srk-extra/official/. $OFFICIAL_DIR/ ..."
  cp -R "$ROOT/srk-extra/official/." "$OFFICIAL_DIR/" \
    || die "叠加 srk-extra 失败"
fi

# ---------------------------------------------------------------------------- #
# 2. 兼容性符号链接 /tmp/srk-collection -> $DATA_HOME
# ---------------------------------------------------------------------------- #
ensure_compat_link() {
  # 已是指向 DATA_HOME 的符号链接：无需改动。
  if [[ -L "$COMPAT_LINK" ]]; then
    local target
    target="$(readlink "$COMPAT_LINK")"
    if [[ "$target" == "$DATA_HOME" ]]; then
      log "兼容符号链接已正确指向源数据目录。"
      return
    fi
    log "兼容符号链接指向 '$target'（非预期），重建中 ..."
    rm -rf "$COMPAT_LINK"
  elif [[ -e "$COMPAT_LINK" ]]; then
    # 存在但不是符号链接（例如真实目录），移除后重建为符号链接。
    log "$COMPAT_LINK 已存在且不是符号链接，移除后重建 ..."
    rm -rf "$COMPAT_LINK"
  fi
  ln -s "$DATA_HOME" "$COMPAT_LINK"
  log "已建立兼容符号链接 $COMPAT_LINK -> $DATA_HOME"
}
ensure_compat_link

# ---------------------------------------------------------------------------- #
# 3. 回放 + 回测（除非 --no-backtest）
# ---------------------------------------------------------------------------- #
if [[ "$DO_BACKTEST" -eq 1 ]]; then
  log "运行回放 + 回测: xcpc_rating.cli --data $OFFICIAL_DIR ..."
  PYTHONPATH=src python3 -m xcpc_rating.cli --data "$OFFICIAL_DIR" \
    || die "回放/回测步骤失败（xcpc_rating.cli）"
else
  log "跳过回放 + 回测（--no-backtest）。"
fi

# ---------------------------------------------------------------------------- #
# 4. 导出 web 数据
# ---------------------------------------------------------------------------- #
log "导出 web 数据: xcpc_rating.export_web --data $OFFICIAL_DIR --out $WEB_DATA_OUT ..."
PYTHONPATH=src python3 -m xcpc_rating.export_web \
  --data "$OFFICIAL_DIR" --out "$WEB_DATA_OUT" \
  || die "web 数据导出失败（xcpc_rating.export_web）"

# ---------------------------------------------------------------------------- #
# 5. 构建前端（除非 --no-build）
# ---------------------------------------------------------------------------- #
if [[ "$DO_BUILD" -eq 1 ]]; then
  log "构建前端: (cd web && npm run build) ..."
  ( cd web && npm run build ) || die "前端构建失败（npm run build）"
else
  log "跳过前端构建（--no-build）。"
fi

# ---------------------------------------------------------------------------- #
# 6. 摘要
# ---------------------------------------------------------------------------- #
log "================ 摘要 ================"

COMMIT_HASH="$(git -C "$DATA_HOME" rev-parse --short HEAD 2>/dev/null || echo '未知')"
COMMIT_DATE="$(git -C "$DATA_HOME" log -1 --format=%cd --date=short 2>/dev/null || echo '未知')"
log "数据仓库 commit: $COMMIT_HASH ($COMMIT_DATE)"

META_FILE="$WEB_DATA_OUT/meta.json"
LB_FILE="$WEB_DATA_OUT/leaderboard.json"

if [[ -f "$META_FILE" ]]; then
  SUMMARY="$(python3 -c "
import json, sys
meta = json.load(open('$META_FILE', encoding='utf-8'))
counts = meta.get('counts', {})
print('contests=%s players=%s ratedPlayers=%s'
      % (counts.get('contests', '?'),
         counts.get('players', '?'),
         counts.get('ratedPlayers', '?')))
" 2>/dev/null || echo '')"
  [[ -n "$SUMMARY" ]] && log "导出规模: $SUMMARY" || log "导出规模: 无法解析 meta.json"
else
  log "导出规模: 未找到 $META_FILE"
fi

if [[ -f "$LB_FILE" ]]; then
  TOP="$(python3 -c "
import json, sys
# leaderboard.json 现为单数组(incremental 阶梯榜,按 rating 降序)。
data = json.load(open('$LB_FILE', encoding='utf-8'))
board = data if isinstance(data, list) else []
if board:
    p = board[0]
    print('%s @ %s  rating=%s  (contests=%s)'
          % (p.get('name', '?'), p.get('org', '?'),
             p.get('rating', '?'), p.get('contests', '?')))
else:
    print('(空榜单)')
" 2>/dev/null || echo '')"
  [[ -n "$TOP" ]] && log "榜首选手: $TOP" || log "榜首选手: 无法解析 leaderboard.json"
else
  log "榜首选手: 未找到 $LB_FILE"
fi

log "====================================="
log "完成。源数据持久化于 ${DATA_HOME}，可随时重跑本脚本更新。"
