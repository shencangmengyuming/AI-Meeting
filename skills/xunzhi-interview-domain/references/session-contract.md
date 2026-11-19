# Interview Session Contract

- Storage collection: `interview_session` in the configured Mongo database.
- A session contains `sessionId`, `userId`, `status`, `conversationTitle`,
  `delFlag`, `createTime`, `updateTime`, and optional start/end timestamps.
- Creating a session abandons the user's active `DRAFT`, `RESUME_UPLOADING`,
  `READY`, and `IN_PROGRESS` sessions before inserting a new `DRAFT` session.
- Finishing a session requires both `sessionId` and authenticated `userId`;
  cross-user access is rejected as not found.
- Session lifecycle state is separate from question-flow state.
- Question cache key: `interview:questions:session:{sessionId}`. Redis hashes
  are sorted numerically by question number; Mongo `interview_question` is the
  recovery source when the cache is empty.
- Flow key: `interview:flow:session:{sessionId}`. It stores `status`,
  `currentQuestionNumber`, `totalQuestions`, and `finished`; reading a question
  initializes an absent flow at question `1` in `ASKING` state.
