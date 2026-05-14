#!/usr/bin/env bash
# ================================================================
#  AIAquaFarm - GitHub Push 스크립트 (Git Bash / WSL / macOS)
#  사용법:
#    bash push.sh
#    또는 chmod +x push.sh && ./push.sh
# ================================================================

GITHUB_USER="tonyk784578"
REPO_NAME="AIAquaFarm_MLOps"
BRANCH="master"

echo ""
echo " ==================================="
echo "  AIAquaFarm GitHub Push"
echo " ==================================="
echo ""

# PAT 입력 (미리 환경변수로 설정해도 됨: export GITHUB_PAT=ghp_xxx)
if [ -z "$GITHUB_PAT" ]; then
    read -rsp "GitHub PAT 입력 (ghp_...): " GITHUB_PAT
    echo ""
fi

if [ -z "$GITHUB_PAT" ]; then
    echo "[오류] PAT가 입력되지 않았습니다."
    exit 1
fi

# 커밋 여부 확인
read -rp "변경사항을 커밋하고 Push하시겠습니까? (y/n): " DO_COMMIT

if [[ "$DO_COMMIT" =~ ^[Yy]$ ]]; then
    read -rp "커밋 메시지 입력 (엔터 = 'update'): " COMMIT_MSG
    COMMIT_MSG="${COMMIT_MSG:-update}"

    git add -A
    git commit -m "$COMMIT_MSG" || echo "[알림] 커밋할 변경사항이 없거나 커밋 실패"
fi

# remote URL에 PAT 포함하여 설정
git remote set-url origin "https://${GITHUB_USER}:${GITHUB_PAT}@github.com/${GITHUB_USER}/${REPO_NAME}.git"

# Push
echo ""
echo "[Push 중...] origin/${BRANCH}"
git push origin "$BRANCH"
PUSH_RESULT=$?

# 보안: remote URL에서 PAT 제거
git remote set-url origin "https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

echo ""
if [ $PUSH_RESULT -eq 0 ]; then
    echo "[완료] Push 성공!"
else
    echo "[실패] Push 실패. PAT 권한 또는 네트워크를 확인하세요."
    exit 1
fi
