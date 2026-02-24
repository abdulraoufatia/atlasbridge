import { db } from "./db";
import { eq } from "drizzle-orm";
import {
  users, groups, roles, apiKeys, securityPolicies, notifications, ipAllowlist, repoConnections, complianceScans,
  type InsertUser, type User,
  type InsertGroup, type Group,
  type InsertRole, type Role,
  type InsertApiKey, type ApiKey,
  type InsertSecurityPolicy, type SecurityPolicy,
  type InsertNotification, type Notification,
  type InsertIpAllowlist, type IpAllowlistEntry,
  type InsertRepoConnection, type RepoConnection,
  type InsertComplianceScan, type ComplianceScan,
} from "@shared/schema";

export interface IStorage {
  getUsers(): Promise<User[]>;
  getUser(id: number): Promise<User | undefined>;
  createUser(data: InsertUser): Promise<User>;
  updateUser(id: number, data: Partial<InsertUser>): Promise<User | undefined>;
  deleteUser(id: number): Promise<boolean>;

  getGroups(): Promise<Group[]>;
  getGroup(id: number): Promise<Group | undefined>;
  createGroup(data: InsertGroup): Promise<Group>;
  updateGroup(id: number, data: Partial<InsertGroup>): Promise<Group | undefined>;
  deleteGroup(id: number): Promise<boolean>;

  getRoles(): Promise<Role[]>;
  getRole(id: number): Promise<Role | undefined>;
  createRole(data: InsertRole): Promise<Role>;
  updateRole(id: number, data: Partial<InsertRole>): Promise<Role | undefined>;
  deleteRole(id: number): Promise<boolean>;

  getApiKeys(): Promise<ApiKey[]>;
  createApiKey(data: InsertApiKey): Promise<ApiKey>;
  updateApiKey(id: number, data: Partial<InsertApiKey>): Promise<ApiKey | undefined>;
  deleteApiKey(id: number): Promise<boolean>;

  getSecurityPolicies(): Promise<SecurityPolicy[]>;
  updateSecurityPolicy(id: number, data: Partial<InsertSecurityPolicy>): Promise<SecurityPolicy | undefined>;

  getNotifications(): Promise<Notification[]>;
  createNotification(data: InsertNotification): Promise<Notification>;
  updateNotification(id: number, data: Partial<InsertNotification>): Promise<Notification | undefined>;
  deleteNotification(id: number): Promise<boolean>;

  getIpAllowlist(): Promise<IpAllowlistEntry[]>;
  createIpAllowlistEntry(data: InsertIpAllowlist): Promise<IpAllowlistEntry>;
  deleteIpAllowlistEntry(id: number): Promise<boolean>;

  getRepoConnections(): Promise<RepoConnection[]>;
  getRepoConnection(id: number): Promise<RepoConnection | undefined>;
  createRepoConnection(data: InsertRepoConnection): Promise<RepoConnection>;
  updateRepoConnection(id: number, data: Partial<InsertRepoConnection>): Promise<RepoConnection | undefined>;
  deleteRepoConnection(id: number): Promise<boolean>;

  getComplianceScans(repoId: number): Promise<ComplianceScan[]>;
  createComplianceScan(data: InsertComplianceScan): Promise<ComplianceScan>;
}

export class DatabaseStorage implements IStorage {
  async getUsers() { return db.select().from(users); }
  async getUser(id: number) { const [u] = await db.select().from(users).where(eq(users.id, id)); return u; }
  async createUser(data: InsertUser) { const [u] = await db.insert(users).values(data).returning(); return u; }
  async updateUser(id: number, data: Partial<InsertUser>) { const [u] = await db.update(users).set(data).where(eq(users.id, id)).returning(); return u; }
  async deleteUser(id: number) { const result = await db.delete(users).where(eq(users.id, id)).returning(); return result.length > 0; }

  async getGroups() { return db.select().from(groups); }
  async getGroup(id: number) { const [g] = await db.select().from(groups).where(eq(groups.id, id)); return g; }
  async createGroup(data: InsertGroup) { const [g] = await db.insert(groups).values(data).returning(); return g; }
  async updateGroup(id: number, data: Partial<InsertGroup>) { const [g] = await db.update(groups).set(data).where(eq(groups.id, id)).returning(); return g; }
  async deleteGroup(id: number) { const result = await db.delete(groups).where(eq(groups.id, id)).returning(); return result.length > 0; }

  async getRoles() { return db.select().from(roles); }
  async getRole(id: number) { const [r] = await db.select().from(roles).where(eq(roles.id, id)); return r; }
  async createRole(data: InsertRole) { const [r] = await db.insert(roles).values(data).returning(); return r; }
  async updateRole(id: number, data: Partial<InsertRole>) { const [r] = await db.update(roles).set(data).where(eq(roles.id, id)).returning(); return r; }
  async deleteRole(id: number) { const result = await db.delete(roles).where(eq(roles.id, id)).returning(); return result.length > 0; }

  async getApiKeys() { return db.select().from(apiKeys); }
  async createApiKey(data: InsertApiKey) { const [k] = await db.insert(apiKeys).values(data).returning(); return k; }
  async updateApiKey(id: number, data: Partial<InsertApiKey>) { const [k] = await db.update(apiKeys).set(data).where(eq(apiKeys.id, id)).returning(); return k; }
  async deleteApiKey(id: number) { const result = await db.delete(apiKeys).where(eq(apiKeys.id, id)).returning(); return result.length > 0; }

  async getSecurityPolicies() { return db.select().from(securityPolicies); }
  async updateSecurityPolicy(id: number, data: Partial<InsertSecurityPolicy>) { const [p] = await db.update(securityPolicies).set(data).where(eq(securityPolicies.id, id)).returning(); return p; }

  async getNotifications() { return db.select().from(notifications); }
  async createNotification(data: InsertNotification) { const [n] = await db.insert(notifications).values(data).returning(); return n; }
  async updateNotification(id: number, data: Partial<InsertNotification>) { const [n] = await db.update(notifications).set(data).where(eq(notifications.id, id)).returning(); return n; }
  async deleteNotification(id: number) { const result = await db.delete(notifications).where(eq(notifications.id, id)).returning(); return result.length > 0; }

  async getIpAllowlist() { return db.select().from(ipAllowlist); }
  async createIpAllowlistEntry(data: InsertIpAllowlist) { const [e] = await db.insert(ipAllowlist).values(data).returning(); return e; }
  async deleteIpAllowlistEntry(id: number) { const result = await db.delete(ipAllowlist).where(eq(ipAllowlist.id, id)).returning(); return result.length > 0; }

  async getRepoConnections() { return db.select().from(repoConnections); }
  async getRepoConnection(id: number) { const [r] = await db.select().from(repoConnections).where(eq(repoConnections.id, id)); return r; }
  async createRepoConnection(data: InsertRepoConnection) { const [r] = await db.insert(repoConnections).values(data).returning(); return r; }
  async updateRepoConnection(id: number, data: Partial<InsertRepoConnection>) { const [r] = await db.update(repoConnections).set(data).where(eq(repoConnections.id, id)).returning(); return r; }
  async deleteRepoConnection(id: number) { const result = await db.delete(repoConnections).where(eq(repoConnections.id, id)).returning(); return result.length > 0; }

  async getComplianceScans(repoId: number) { return db.select().from(complianceScans).where(eq(complianceScans.repoConnectionId, repoId)); }
  async createComplianceScan(data: InsertComplianceScan) { const [s] = await db.insert(complianceScans).values(data).returning(); return s; }
}

export const storage = new DatabaseStorage();
