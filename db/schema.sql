-- 研岸 Ashore：建库 + 四张核心表（D1）
CREATE DATABASE IF NOT EXISTS ashore DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ashore;

-- 1. 题库 questions：一道题归属一个知识点（支撑检索/出题/批改）
CREATE TABLE IF NOT EXISTS questions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  subject VARCHAR(64) NOT NULL COMMENT '学科',
  chapter VARCHAR(128) NOT NULL COMMENT '章节',
  knowledge_point VARCHAR(128) NOT NULL COMMENT '知识点',
  question_type VARCHAR(32) NOT NULL COMMENT '题型：选择/填空/计算/简答',
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

