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

`.env` 파일에서 **반드시** 설정해야 하는 값:

```bash
# JWT 토큰 서명 시크릿 (openssl rand -hex 32)
SECRET_KEY=<32자 이상 랜덤>

# 리프레시 토큰용 별도 시크릿 (SECRET_KEY와 다른 값)
JWT_REFRESH_SECRET_KEY=<32자 이상 랜덤, SECRET_KEY와 다른 값>

# 에이전트 ↔ 백엔드 서비스 인증 키 (양쪽 동일하게 설정)
INTERNAL_API_KEY=<랜덤>
BACKEND_API_KEY=<INTERNAL_API_KEY와 동일한 값>

# LangGraph 에이전트 (AI 에이전트 사용 시 필수)
ANTHROPIC_API_KEY=sk-ant-...
```

> **보안 주의**: `SECRET_KEY`와 `JWT_REFRESH_SECRET_KEY`는 반드시 서로 다른 값으로 설정하세요.
> 단일 시크릿 노출 시 공격 범위를 제한하기 위한 설계입니다.

### 1-3. 서비스 시작

```bash
make build    # Docker 이미지 빌드
make up       # 서비스 시작
make migrate  # Alembic DB 마이그레이션
make seed     # 테스트 데이터 주입 (선택)
```

---

## 2. 첫 번째 슈퍼유저 등록

회원가입은 기본적으로 비활성화(`REGISTRATION_OPEN=false`)되어 있습니다.
초기 슈퍼유저 생성 시에만 일시적으로 활성화하세요:

```bash
# 일시적으로 등록 열기
REGISTRATION_OPEN=true make up

# POST /api/v1/auth/register 로 슈퍼유저 생성 후 반드시 비활성화
REGISTRATION_OPEN=false make up
```

---

## 3. 개발 환경

### 핫 리로드 모드

```bash
make dev
```

### 프론트엔드 로컬 dev 서버

Docker 이미지 재빌드 없이 최신 UI 변경사항을 즉시 확인하려면:

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
               # /api → localhost:8000, /agents → localhost:8001 자동 프록시
```

### Mock 데이터 모드 (백엔드 없이 UI 개발)

```bash
# frontend/.env.local
VITE_USE_MOCK=true
```

설정 후 `npm run dev` 실행 시 모든 API 호출이 `src/mocks/` 목 데이터로 intercept됩니다.
실제 네트워크 요청이 발생하지 않으므로 백엔드·DB 없이 전체 UI를 시연할 수 있습니다.

### 개별 서비스 시작

```bash
docker compose up -d postgres redis          # DB만 시작
docker compose up -d postgres redis mlflow   # MLOps 포함
```

### 백엔드 로컬 개발

```bash
cd backend
pip install -e ".[dev]"
DATABASE_URL=postgresql+asyncpg://aquafarm:aquafarm_secret@localhost:5432/aquafarm \
  uvicorn app.main:app --reload
```

---

## 4. 데이터베이스 관리

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

## 5. MLflow 모델 관리

### MLflow UI 접속

```
http://localhost:5000
```

### 학습 스크립트 실행

```bash
# 수질 예측 모델
python mlops/training/train_water.py --mlflow-uri http://localhost:5000 --epochs 100

# 급이 활성도 분류기
python mlops/training/train_feeding.py --mlflow-uri http://localhost:5000

# 어류 성장 감지 모델
python mlops/training/train_growth.py --mlflow-uri http://localhost:5000
```

### AutoML 실행 (자동 재훈련)

```bash
python -m mlops.training.automl \
    --mlflow-uri http://localhost:5000 \
    --data-dir /data \
    --dry-run    # 실제 훈련 없이 조건만 확인
```

재훈련 임계값:

| 모델 | 신규 샘플 수 | PSI 드리프트 |
|------|------------|-------------|
| FishDetection | 500장 | ≥ 0.20 |
| FeedingActivityClassifier | 300장 | ≥ 0.20 |
| WaterQualityPredictor | 1,000행 | ≥ 0.20 |

---

## 6. 합성 테스트 데이터 생성

실제 장비 없이 테스트 데이터를 생성할 수 있습니다:

```bash
python scripts/generate_wq_test_data.py --days 30 --tanks 3 --output data/wq.csv
python scripts/generate_feeding_test_data.py --output data/feeding_dataset/ --n-per-class 200
python scripts/generate_growth_test_data.py --output data/growth_dataset/ --n-train 800
```

---

## 7. 모니터링 및 운영

### 서비스 상태 확인

```bash
make health       # 헬스체크
make ps           # 컨테이너 상태
make logs         # 전체 로그
make logs-backend # 백엔드 로그만
make logs-agents  # 에이전트 로그만
```

### 알림 임계값 조정

`.env` 파일에서 수정 후 `make restart`:

```bash
AMMONIA_THRESHOLD_PPM=0.5      # 암모니아 경고 임계값 (ppm)
NITRITE_THRESHOLD_PPM=0.1      # 아질산 경고 임계값 (ppm)
DISSOLVED_OXYGEN_MIN_MGL=6.0   # 용존산소 최솟값 (mg/L)
PH_MIN=6.5                     # pH 최솟값
PH_MAX=8.5                     # pH 최댓값
TEMPERATURE_MIN_C=18.0         # 수온 최솟값 (°C)
TEMPERATURE_MAX_C=28.0         # 수온 최댓값 (°C)
```

---

## 8. 트러블슈팅

### PostgreSQL 연결 실패

```bash
docker compose logs postgres
docker compose exec postgres pg_isready -U aquafarm
```

### TimescaleDB 초기화 확인

Hypertable은 `infra/postgres/init.sql`이 DB 최초 생성 시 자동 적용됩니다.
수동 확인:

```bash
docker compose exec postgres psql -U aquafarm -c \
  "SELECT hypertable_name FROM timescaledb_information.hypertables;"
```

`water_quality_readings`, `fish_growth_records`, `feeding_records` 가 보여야 합니다.

### MLflow DB 연결 실패

MLflow는 별도의 `aquafarm_mlflow` DB를 사용합니다:

```bash
docker compose exec postgres psql -U aquafarm -c "\l"
# aquafarm_mlflow 가 있는지 확인
```

### Redis pub/sub 연결 실패

WebSocket 또는 제어 명령이 동작하지 않을 경우:

```bash
docker compose exec redis redis-cli ping   # PONG 반환 확인
docker compose exec redis redis-cli subscribe wq:TANK-01  # 채널 구독 테스트
```

### 포트 충돌

| 서비스 | 포트 |
|--------|------|
| Nginx (프론트엔드) | 80 |
| Backend (FastAPI) | 8000 |
| Agents (LangGraph) | 8001 |
| MLflow | 5000 |
| PostgreSQL | 5432 |
| Redis | 6379 |

---

## 9. 프로덕션 배포 체크리스트

### 필수 보안 설정

- [ ] `SECRET_KEY` 강력한 랜덤값 (`openssl rand -hex 32`)
- [ ] `JWT_REFRESH_SECRET_KEY` SECRET_KEY와 **다른** 별도 랜덤값
- [ ] `INTERNAL_API_KEY` / `BACKEND_API_KEY` 동일한 랜덤 시크릿으로 설정
- [ ] `REGISTRATION_OPEN=false` 확인 (기본값)
- [ ] `COOKIE_SECURE=true` (HTTPS 환경 필수)
- [ ] `POSTGRES_PASSWORD` 기본값에서 변경
- [ ] `DEBUG=false` 확인

### 네트워크 / 인프라

- [ ] Nginx HTTPS 설정 (Let's Encrypt 또는 자체 인증서)
- [ ] `CORS_ORIGINS` 실제 도메인으로 제한
- [ ] MLflow 외부 접근 차단 또는 인증 추가

### 데이터 / 운영

- [ ] S3 버킷 설정 (`S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`)
- [ ] 백업 정책 설정 (PostgreSQL WAL, S3 versioning)
- [ ] K8s Secrets에 실제 값 주입 (Sealed Secrets 또는 External Secrets Operator)
