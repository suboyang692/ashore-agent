-- 研岸 Ashore：建库 + 建核心表
CREATE DATABASE IF NOT EXISTS ashore DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ashore;

-- 1. 题库 questions：一道题归属一个知识点（支撑检索/出题/批改）
CREATE TABLE IF NOT EXISTS questions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  subject VARCHAR(64) NOT NULL COMMENT '学科',
  chapter VARCHAR(128) NOT NULL COMMENT '章节',
  knowledge_point VARCHAR(128) NOT NULL COMMENT '知识点',
  question_type ENUM('选择','填空','解答') NOT NULL COMMENT '题型，三选一；判分分流依赖它（见 app/question_types.py）',
  stem TEXT NOT NULL COMMENT '题干',
  answer TEXT COMMENT '标准答案',
  analysis TEXT COMMENT '解析',
  difficulty TINYINT DEFAULT 3 COMMENT '难度1-5',
  source VARCHAR(128) COMMENT '来源，如：2019年真题/自编模拟',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_subject (subject),
  INDEX idx_kp (knowledge_point)
) ENGINE=InnoDB COMMENT='题库';

-- 2. 答题记录 answer_records：用户每次作答（支撑批改 Agent 与错题归类）
CREATE TABLE IF NOT EXISTS answer_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL COMMENT '用户标识',
  question_id INT NOT NULL,
  user_answer TEXT COMMENT '用户作答原文',
  is_correct TINYINT DEFAULT 0 COMMENT '1对0错',
  score DECIMAL(5,2) COMMENT '得分',
  mistake_type VARCHAR(32) COMMENT '错因：计算错误/结论跳跃/指令不遵循等',
  mistake_detail TEXT COMMENT '错误原文-出错原因-正确写法',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user (user_id),
  INDEX idx_qid (question_id),
  CONSTRAINT fk_ans_q FOREIGN KEY (question_id) REFERENCES questions(id)
) ENGINE=InnoDB COMMENT='答题记录';

-- 3. 学情画像 user_mastery：用户 x 知识点掌握度（支撑规划 Agent）
CREATE TABLE IF NOT EXISTS user_mastery (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  knowledge_point VARCHAR(128) NOT NULL,
  total_count INT DEFAULT 0 COMMENT '练习次数',
  wrong_count INT DEFAULT 0 COMMENT '错误次数',
  mastery DECIMAL(4,2) DEFAULT 0.00 COMMENT '掌握度0-1',
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_kp (user_id, knowledge_point)
) ENGINE=InnoDB COMMENT='学情画像';

-- 4. 评测标注 eval_annotations：检索/批改/出题标注与 badcase（支撑评测闭环）
CREATE TABLE IF NOT EXISTS eval_annotations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  task_type VARCHAR(32) NOT NULL COMMENT '任务类型：检索/批改/出题/端到端',
  input_text TEXT COMMENT '输入',
  expected_output TEXT COMMENT '期望结果',
  actual_output TEXT COMMENT '模型实际输出',
  is_pass TINYINT DEFAULT 0 COMMENT '1通过0失败',
  badcase_reason VARCHAR(255) COMMENT '失败归因',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task (task_type)
) ENGINE=InnoDB COMMENT='评测标注';

-- 5. 复习计划 review_plans：规划 Agent 产出（支撑「学-练-测-评-规」闭环）
CREATE TABLE IF NOT EXISTS review_plans (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL COMMENT '用户标识',
  days INT NOT NULL COMMENT '计划天数',
  summary TEXT COMMENT '学情诊断',
  content LONGTEXT COMMENT '逐日计划明细（JSON）',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user (user_id)
) ENGINE=InnoDB COMMENT='复习计划';

-- 6. 用户 users：为登录、权限和用户数据隔离预留统一身份
CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(64) PRIMARY KEY,
  username VARCHAR(64) NOT NULL,
  email VARCHAR(255) NULL,
  password_hash VARCHAR(255) NULL,
  role ENUM('student','admin') NOT NULL DEFAULT 'student',
  status ENUM('active','disabled') NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  last_login_at DATETIME NULL,
  UNIQUE KEY uk_users_username (username),
  UNIQUE KEY uk_users_email (email),
  INDEX idx_users_status (status)
) ENGINE=InnoDB COMMENT='用户与权限主体';

-- 7. 会话与消息：长期事实数据，Redis 只做缓存
CREATE TABLE IF NOT EXISTS conversations (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  title VARCHAR(255) NOT NULL DEFAULT '新会话',
  summary TEXT NULL,
  status ENUM('active','archived','deleted') NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_conversations_user_updated (user_id, updated_at),
  CONSTRAINT fk_conversations_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='长期会话';

CREATE TABLE IF NOT EXISTS conversation_messages (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  conversation_id BIGINT NOT NULL,
  role ENUM('system','user','assistant','tool') NOT NULL,
  content LONGTEXT NOT NULL,
  agent_name VARCHAR(64) NULL,
  tool_name VARCHAR(64) NULL,
  request_id VARCHAR(64) NULL,
  latency_ms INT UNSIGNED NULL,
  input_tokens INT UNSIGNED NULL,
  output_tokens INT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_messages_conversation_created (conversation_id, created_at),
  INDEX idx_messages_request (request_id),
  CONSTRAINT fk_messages_conversation FOREIGN KEY (conversation_id) REFERENCES conversations(id)
) ENGINE=InnoDB COMMENT='会话消息';

-- 8. 答题与错因：一次尝试可关联多个错误点
CREATE TABLE IF NOT EXISTS practice_attempts (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL,
  question_id INT NOT NULL,
  answer_text LONGTEXT NULL,
  grading_status ENUM('pending','graded','failed') NOT NULL DEFAULT 'pending',
  is_correct TINYINT NULL,
  score DECIMAL(5,2) NULL,
  request_id VARCHAR(64) NULL,
  started_at DATETIME NULL,
  submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  graded_at DATETIME NULL,
  UNIQUE KEY uk_attempt_request (request_id),
  INDEX idx_attempts_user_time (user_id, submitted_at),
  INDEX idx_attempts_question (question_id),
  CONSTRAINT fk_attempts_question FOREIGN KEY (question_id) REFERENCES questions(id)
) ENGINE=InnoDB COMMENT='答题尝试';

CREATE TABLE IF NOT EXISTS mistake_records (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  attempt_id BIGINT NOT NULL,
  knowledge_point VARCHAR(128) NULL,
  mistake_type VARCHAR(32) NOT NULL,
  original_text TEXT NULL,
  reason TEXT NULL,
  correct_method TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_mistakes_attempt (attempt_id),
  INDEX idx_mistakes_type_kp (mistake_type, knowledge_point),
  CONSTRAINT fk_mistakes_attempt FOREIGN KEY (attempt_id) REFERENCES practice_attempts(id)
) ENGINE=InnoDB COMMENT='错因明细';

-- 9. 复习计划任务：把 content JSON 逐步拆成可追踪明细
CREATE TABLE IF NOT EXISTS review_plan_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  plan_id INT NOT NULL,
  day_no INT NOT NULL,
  knowledge_point VARCHAR(128) NOT NULL,
  task_type VARCHAR(32) NOT NULL,
  question_id INT NULL,
  target_count INT NOT NULL DEFAULT 1,
  completed_count INT NOT NULL DEFAULT 0,
  status ENUM('pending','in_progress','completed','overdue') NOT NULL DEFAULT 'pending',
  due_at DATETIME NULL,
  completed_at DATETIME NULL,
  INDEX idx_plan_items_plan_day (plan_id, day_no),
  INDEX idx_plan_items_status (status),
  CONSTRAINT fk_plan_items_plan FOREIGN KEY (plan_id) REFERENCES review_plans(id),
  CONSTRAINT fk_plan_items_question FOREIGN KEY (question_id) REFERENCES questions(id)
) ENGINE=InnoDB COMMENT='复习计划任务明细';

-- 10. 知识库文档、版本与切片元数据
CREATE TABLE IF NOT EXISTS documents (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  owner_id VARCHAR(64) NULL,
  title VARCHAR(255) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  file_hash CHAR(64) NOT NULL,
  source_type ENUM('lecture','exam','user_upload') NOT NULL DEFAULT 'lecture',
  status ENUM('pending','processing','ready','failed','archived') NOT NULL DEFAULT 'pending',
  error_message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_documents_hash (file_hash),
  INDEX idx_documents_status (status),
  CONSTRAINT fk_documents_owner FOREIGN KEY (owner_id) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='知识库文档';

CREATE TABLE IF NOT EXISTS document_versions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  document_id BIGINT NOT NULL,
  version_no INT NOT NULL,
  parser_version VARCHAR(64) NULL,
  embedding_model VARCHAR(128) NULL,
  chunk_strategy VARCHAR(128) NULL,
  status ENUM('processing','ready','failed','rolled_back') NOT NULL DEFAULT 'processing',
  error_message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  UNIQUE KEY uk_document_version (document_id, version_no),
  CONSTRAINT fk_versions_document FOREIGN KEY (document_id) REFERENCES documents(id)
) ENGINE=InnoDB COMMENT='知识库文档版本';

CREATE TABLE IF NOT EXISTS document_chunks (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  document_version_id BIGINT NOT NULL,
  chunk_no INT NOT NULL,
  content LONGTEXT NOT NULL,
  chapter VARCHAR(128) NULL,
  knowledge_point VARCHAR(128) NULL,
  page_no INT NULL,
  vector_id VARCHAR(255) NULL,
  content_hash CHAR(64) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_chunk_no (document_version_id, chunk_no),
  INDEX idx_chunks_kp (knowledge_point),
  INDEX idx_chunks_vector (vector_id),
  CONSTRAINT fk_chunks_version FOREIGN KEY (document_version_id) REFERENCES document_versions(id)
) ENGINE=InnoDB COMMENT='知识库切片元数据';

-- 11. 异步任务：OCR、入库、出题和评测统一跟踪
CREATE TABLE IF NOT EXISTS jobs (
  id CHAR(36) PRIMARY KEY,
  user_id VARCHAR(64) NULL,
  job_type VARCHAR(32) NOT NULL,
  status ENUM('pending','running','success','failed','cancelled') NOT NULL DEFAULT 'pending',
  progress TINYINT UNSIGNED NOT NULL DEFAULT 0,
  payload JSON NULL,
  result JSON NULL,
  error_message TEXT NULL,
  retry_count TINYINT UNSIGNED NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  INDEX idx_jobs_user_created (user_id, created_at),
  INDEX idx_jobs_status (status),
  CONSTRAINT fk_jobs_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB COMMENT='异步任务';

