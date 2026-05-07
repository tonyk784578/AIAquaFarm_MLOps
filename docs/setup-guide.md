# AIAquafarm 설치 및 운영 가이드

## 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Ubuntu 20.04 / macOS 12 | Ubuntu 22.04 |
| CPU | 4코어 | 8코어+ |
| RAM | 8GB | 16GB+ |
| Disk | 20GB | 50GB+ (데이터 레이크) |
| Docker | 24.0+ | 최신 |
| Docker Compose | 2.20+ | 최신 |

---

## 1. 초기 설치

### 1-1. 저장소 클론
```bash
git clone https://github.com/your-org/aiaquafarm.git
cd aiaquafarm
```

### 1-2. 환경변수 설정
```bash
cp .env.example .env
```

`.env` 파일에서 반드시 설정해야 하는 값:
```bash
SECRET_KEY=<최소 32자 랜덤 문자열>
ANTHROPIC_API_KEY=sk-ant-...   # LangGraph 에이전트 사용 시
```

### 1-3. 자동 설치 스크립트
```bash
bash scripts/setup.sh
```

또는 수동으로:
```bash
make build    # Docker 이미지 빌드
make up       # 서비스 시작
make migrate  # DB 마이그레이션
make seed     # 테스트 데이터 주입 (옵션)
```

---

## 2. 개발 환경

### 핫 리로드 모드
```bash
make dev
```

### 개별 서비스 시작
```bash
docker compose up -d postgres redis          # DB만 시작
docker compose up -d postgres redis mlflow   # MLOps 포함
```

### 백엔드 개발 (로컬)
```bash
cd backend
pip install -e ".[dev]"
DATABASE_URL=postgresql+asyncpg://aquafarm:aquafarm_secret@localhost:5432/aquafarm \
  uvicorn app.main:app --reload
```

---

## 3. 데이터베이스 관리

### 마이그레이션 생성
```bash
make makemigration MSG="add_tank_config_table"
```

### 마이그레이션 적용
```bash
make migrate
```

### TimescaleDB 확장 확인
```bash
docker compose exec postgres psql -U aquafarm -c "\dx"
```
`timescaledb`가 목록에 있어야 합니다.

---

## 4. MLflow 모델 관리

### MLflow UI 접속
```
http://localhost:5000
```

### 모델 등록 (학습 완료 후)
```python
import mlflow
mlflow.set_tracking_uri("http://localhost:5000")
mlflow.set_experiment("fish-growth-detection")

with mlflow.start_run():
    # ... 학습 코드 ...
    mlflow.pytorch.log_model(model, "model",
                             registered_model_name="FishDetection")
```

---

## 5. 모니터링 및 운영

### 서비스 상태 확인
```bash
make health      # 헬스체크
make ps          # 컨테이너 상태
make logs        # 전체 로그
make logs-backend # 백엔드 로그만
```

### 알림 임계값 조정
`.env` 파일에서 수정:
```bash
AMMONIA_THRESHOLD_PPM=0.5    # 암모니아 경고 임계값
NITRITE_THRESHOLD_PPM=0.1    # 아질산 경고 임계값
DISSOLVED_OXYGEN_MIN_MGL=6.0 # 용존산소 최솟값
```
변경 후 `make restart` 적용.

---

## 6. 트러블슈팅

### PostgreSQL 연결 실패
```bash
docker compose logs postgres
# → pg_isready 확인
docker compose exec postgres pg_isready -U aquafarm
```

### TimescaleDB 초기화 실패
Hypertable은 테이블 생성 후 변환됩니다. 순서:
1. `make migrate` (SQLAlchemy 테이블 생성)
2. `infra/postgres/init.sql` DO 블록 수동 실행

### MLflow 데이터베이스 연결 실패
MLflow는 별도의 `aquafarm_mlflow` DB를 사용합니다:
```bash
docker compose exec postgres psql -U aquafarm -c "\l"
# aquafarm_mlflow 있는지 확인
```

### 포트 충돌
| 서비스 | 포트 |
|--------|------|
| Nginx | 80 |
| Backend | 8000 |
| MLflow | 5000 |
| PostgreSQL | 5432 |
| Redis | 6379 |

---

## 7. 프로덕션 배포 체크리스트

- [ ] `SECRET_KEY` 강력한 랜덤값으로 변경
- [ ] `POSTGRES_PASSWORD` 변경
- [ ] `DEBUG=false` 확인
- [ ] Nginx HTTPS 설정 (Let's Encrypt)
- [ ] S3 버킷 설정 (데이터 레이크)
- [ ] MLflow 외부 접근 차단 또는 인증 추가
- [ ] 백업 정책 설정 (PostgreSQL WAL, S3 versioning)
