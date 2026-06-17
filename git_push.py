#!/usr/bin/env python3
"""可靠地推送本地更改到 GitHub"""
import subprocess, os, sys

WORK_DIR = '/Users/hesterzhang/Desktop/具身智能网页'
LOG_FILE = os.path.join(WORK_DIR, 'git_push_log.txt')

os.chdir(WORK_DIR)

with open(LOG_FILE, 'w', encoding='utf-8') as log:
    def log_cmd(cmd, result):
        log.write(f'\n=== {" ".join(cmd)} ===\n')
        log.write(f'  exit: {result.returncode}\n')
        if result.stdout:
            log.write(f'  stdout: {result.stdout[:1000]}\n')
        if result.stderr:
            log.write(f'  stderr: {result.stderr[:1000]}\n')
    
    # 1. 设置 git 用户信息
    log.write('Step 1: 设置 git 配置\n')
    r = subprocess.run(['git', 'config', 'user.name', 'AI Assistant'], capture_output=True, text=True)
    log_cmd(['git', 'config', 'user.name'], r)
    r = subprocess.run(['git', 'config', 'user.email', 'ai@assistant.local'], capture_output=True, text=True)
    log_cmd(['git', 'config', 'user.email'], r)
    
    # 2. 检查状态
    log.write('Step 2: git status\n')
    r = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
    log_cmd(['git', 'status'], r)
    has_changes = bool(r.stdout.strip())
    log.write(f'  有未提交的更改: {has_changes}\n')
    
    # 3. commit
    if has_changes:
        log.write('Step 3: git add + commit\n')
        r = subprocess.run(['git', 'add', '-A'], capture_output=True, text=True)
        log_cmd(['git', 'add', '-A'], r)
        r = subprocess.run(['git', 'commit', '-m', '更新：表格样式+公司增删+新闻筛选'], capture_output=True, text=True)
        log_cmd(['git', 'commit'], r)
    else:
        log.write('Step 3: 没有需要提交的更改（更改可能已经 commit 了）\n')
    
    # 4. push
    log.write('Step 4: git push\n')
    log.write('  尝试 HTTPS push...\n')
    r = subprocess.run(['git', 'push', 'origin', 'main'], capture_output=True, text=True, timeout=60)
    log_cmd(['git', 'push', 'origin', 'main'], r)
    
    # 5. 验证
    log.write('Step 5: 验证\n')
    r = subprocess.run(['git', '--no-pager', 'log', '--oneline', '-3'], capture_output=True, text=True)
    log_cmd(['git', 'log'], r)
    r = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True)
    log.write(f'  本地 HEAD: {r.stdout.strip()}\n')
    r = subprocess.run(['git', 'rev-parse', 'origin/main'], capture_output=True, text=True)
    log.write(f'  远程 main: {r.stdout.strip()}\n')
    
    log.write('\n=== 完成 ===\n')

print(f'已写入日志到 {LOG_FILE}')
