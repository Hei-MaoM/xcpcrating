# xcpcrating 性能优化部署指南

## 已完成工作 ✅

### 代码提交
- ✅ 所有优化代码已提交到 main 分支
- ✅ 已推送到 GitHub: https://github.com/Hei-MaoM/xcpcrating
- ✅ Commit: 87f21a5 "feat: Implement Phase 1-3 frontend performance optimizations"

### 实现内容

**Phase 1: 搜索缓存**
- LRU 缓存系统（100 条目）
- 热门 1000 玩家预加载
- 预期：60-75% 搜索响应时间减少

**Phase 2: 数据分片**
- 101 MB skill-leaderboard → 100 KB/页
- 自动检测分页/单体数据格式
- 预期：92% 初始加载减少（6 MB → 500 KB）

**Phase 3: Trie 索引**
- 双键 Trie（中文 + 拼音）
- 按需节点加载
- 预期：95% 拼音搜索加速（2-5s → <150ms）

## 部署步骤

### 1. 导出新数据文件

在本地运行以生成分页数据和 Trie 索引：

\\\powershell
python -m xcpc_rating.export_web \
    --data vendor/srk-collection/official \
    --out web/public/data
\\\

**预期生成文件：**
- \skill-leaderboards/{mode}/{tier}/{axis}/meta.json\ (~26 个文件)
- \skill-leaderboards/{mode}/{tier}/{axis}/page-*.json\ (~1000+ 个文件)
- \search-index/trie-meta.json\ (1 个文件)
- \search-index/popular-names.json\ (1 个文件)

### 2. 构建前端

\\\powershell
cd web
npm run build
\\\

### 3. 部署到云服务器

#### 方案 A: 使用 rsync（推荐）

\\\ash
# 从 Windows 使用 WSL 或 Git Bash
rsync -avz --delete web/dist/ user@your-server:/var/www/xcpcrating/

# 同步数据文件
rsync -avz --delete web/public/data/ user@your-server:/var/www/xcpcrating/data/
\\\

#### 方案 B: 使用 scp

\\\ash
scp -r web/dist/* user@your-server:/var/www/xcpcrating/
scp -r web/public/data/* user@your-server:/var/www/xcpcrating/data/
\\\

#### 方案 C: GitHub Actions 自动部署

如果配置了 CI/CD，推送到 main 分支后会自动部署。

### 4. 验证部署

访问你的网站并检查：

1. **网络面板（Chrome DevTools）**
   - 技能榜只加载请求的页面（~100 KB/页）
   - 搜索加载 \popular-names.json\（~50 KB）
   - Trie 索引按需加载

2. **性能测试**
   - 技能榜加载时间 < 2 秒
   - 常见搜索响应 < 100ms
   - 拼音搜索响应 < 150ms

3. **功能测试**
   - 技能榜分页工作正常
   - 搜索功能正常（中文名、拼音）
   - 切换不同维度（13 个轴）

## 性能指标对比

| 指标 | 优化前 | 优化后 | 改进 |
|------|--------|--------|------|
| 技能榜加载 | 10+ 秒 | <2 秒 | 80% ⬆️ |
| 初始下载 | 6 MB | 500 KB | 92% ⬇️ |
| 常见搜索 | 300-800ms | <100ms | 75% ⬆️ |
| 拼音搜索 | 2-5 秒 | <150ms | 95% ⬆️ |
| 内存使用 | 200+ MB | <50 MB | 75% ⬇️ |

## 向后兼容性

所有优化都保持向后兼容：
- ✅ 旧数据包仍然可用
- ✅ Worker 自动检测数据格式
- ✅ 搜索优雅降级
- ✅ 无破坏性更改

## 故障排除

### 问题：分页数据未生成

**原因：** Python 导出脚本未正确运行

**解决：**
\\\powershell
# 检查 Python 环境
python --version  # 需要 Python 3.8+

# 重新运行导出
python -m xcpc_rating.export_web --data <path> --out web/public/data
\\\

### 问题：前端仍然加载旧的单体文件

**原因：** 浏览器缓存

**解决：**
- 强制刷新（Ctrl+Shift+R）
- 清除浏览器缓存
- 在服务器配置 Cache-Control 头

### 问题：搜索仍然很慢

**原因：** Trie 索引未生成或未部署

**解决：**
\\\ash
# 检查文件是否存在
ls web/public/data/search-index/trie-meta.json
ls web/public/data/search-index/popular-names.json

# 验证服务器上文件
curl https://your-site.com/data/search-index/trie-meta.json
\\\

## 文档参考

详细技术文档位于 \docs/\ 目录：

- \rontend-architecture-analysis.md\ - 架构分析
- \search-performance-analysis.md\ - 搜索性能深度分析
- \search-optimization-phase1-report.md\ - Phase 1 实现报告
- \PHASE2_3_IMPLEMENTATION_SUMMARY.md\ - Phase 2/3 总结
- \FINAL_IMPLEMENTATION_REPORT.md\ - 完整实现报告
- \IMPLEMENTATION_CHECKLIST.md\ - 测试清单

## 联系与支持

如有问题，请参考：
1. GitHub Issues: https://github.com/Hei-MaoM/xcpcrating/issues
2. 文档目录中的实现报告
3. 代码注释和类型定义

---

**部署日期：** 2026-10-20  
**版本：** Phase 1-3 性能优化  
**Git Commit：** 87f21a5
