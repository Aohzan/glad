CREATE TABLE "user" (
  "id" integer PRIMARY KEY,
  "email" varchar NOT NULL,
  "full_name" varchar,
  "hashed_password" varchar,
  "is_active" bool DEFAULT true,
  "is_superuser" bool DEFAULT false,
  "group_id" integer,
  "created_at" timestamp
);

CREATE TABLE "user_group" (
  "owner_id" integer,
  "id" integer PRIMARY KEY
);

CREATE TABLE "account" (
  "id" integer PRIMARY KEY,
  "subcategory" varchar NOT NULL,
  "name" varchar NOT NULL,
  "group_id" integer NOT NULL,
  "is_active" bool DEFAULT true,
  "currency" varchar NOT NULL,
  "created_at" timestamp,
  "updated_at" timestamp
);

CREATE TABLE "account_balance" (
  "id" integer PRIMARY KEY,
  "account_id" integer NOT NULL,
  "balance" float NOT NULL,
  "balance_date" datetime,
  "created_at" timestamp,
  "updated_at" timestamp
);

CREATE TABLE "account_holding" (
  "id" integer PRIMARY KEY,
  "account_id" integer NOT NULL,
  "name" varchar NOT NULL,
  "created_at" timestamp,
  "updated_at" timestamp
);

CREATE TABLE "account_holding_balance" (
  "id" integer PRIMARY KEY,
  "account_holding_id" integer NOT NULL,
  "balance" float NOT NULL,
  "balance_date" datetime,
  "created_at" timestamp,
  "updated_at" timestamp
);

ALTER TABLE "user_group" ADD FOREIGN KEY ("id") REFERENCES "user" ("group_id");

ALTER TABLE "user" ADD FOREIGN KEY ("id") REFERENCES "user_group" ("owner_id");

ALTER TABLE "user_group" ADD FOREIGN KEY ("id") REFERENCES "account" ("group_id");

ALTER TABLE "account" ADD FOREIGN KEY ("id") REFERENCES "account_balance" ("account_id");

ALTER TABLE "account" ADD FOREIGN KEY ("id") REFERENCES "account_holding" ("account_id");

ALTER TABLE "account_holding" ADD FOREIGN KEY ("id") REFERENCES "account_holding_balance" ("account_holding_id");