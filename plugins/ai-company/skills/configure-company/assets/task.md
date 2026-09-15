# [업무ID — 업무명]

## 메타

```yaml
status: pending
# pending | in_progress | waiting_<세션> | reviewing | done  (agentlayer가 자동 갱신 — 손으로 고치지 말 것)
# 보드 열: todo=pending(부모 미완) ready=pending(부모 전부 done) running=in_progress blocked=waiting_* review=reviewing done=done
parents: []
# 선행 업무ID 목록. 예: parents: [VIDEO-07-TOPICS]. 전부 done이면 총괄 수신함에 READY 이벤트가 온다.
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
priority: medium
```

## 목표
한 문장. 무엇이 되면 완료인가.

## 담당·순서
- 1단계: <부서/직원> → 산출물 경로
- 2단계: <부서/직원> → 산출물 경로

## 완료 기준
- [ ] 기준 1
