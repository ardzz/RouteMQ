-- Private schema for scripts/smoke_docker.py. Queue tables mirror routemq/queue/models.py;
-- smoke_results mirrors the fixture app/models/smoke_result.py.

CREATE TABLE queue_jobs (
    id INT NOT NULL AUTO_INCREMENT,
    queue VARCHAR(255) NOT NULL,
    payload TEXT NOT NULL,
    attempts INT NOT NULL,
    reserved_at DATETIME NULL,
    available_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    INDEX ix_queue_jobs_queue (queue),
    INDEX queue_jobs_queue_reserved_at_index (queue, reserved_at)
);

CREATE TABLE queue_failed_jobs (
    id INT NOT NULL AUTO_INCREMENT,
    `connection` VARCHAR(255) NOT NULL,
    queue VARCHAR(255) NOT NULL,
    payload TEXT NOT NULL,
    exception TEXT NOT NULL,
    failed_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    INDEX ix_queue_failed_jobs_queue (queue)
);

CREATE TABLE smoke_results (
    message_id VARCHAR(64) NOT NULL,
    `value` VARCHAR(255) NOT NULL,
    worker_hostname VARCHAR(255) NOT NULL,
    PRIMARY KEY (message_id)
);
