import { db } from "./db";
import { eq } from "drizzle-orm";
import {
  users, groups, roles, apiKeys, securityPolicies, notifications, ipAllowlist, repoConnections, qualityScans, rbacPermissions,
  localScans, authProviders, containerScans, infraScans,
  type InsertUser, type User,
  type InsertGroup, type Group,
  type InsertRole, type Role,
  type InsertApiKey, type ApiKey,
  type InsertSecurityPolicy, type SecurityPolicy,
  type InsertNotification, type Notification,
  type InsertIpAllowlist, type IpAllowlistEntry,
  type InsertRepoConnection, type RepoConnection,
  type InsertQualityScan, type QualityScan,
  type InsertRbacPermission, type RbacPermissionRow,
  type InsertLocalScan, type LocalScan,
  type InsertAuthProvider, type AuthProvider,
  type InsertContainerScan, type ContainerScan,
  type InsertInfraScan, type InfraScan,
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

  getQualityScans(repoId: number): Promise<QualityScan[]>;
  createQualityScan(data: InsertQualityScan): Promise<QualityScan>;

  getRbacPermissions(): Promise<RbacPermissionRow[]>;
  createRbacPermission(data: InsertRbacPermission): Promise<RbacPermissionRow>;
  updateRbacPermission(id: number, data: Partial<InsertRbacPermission>): Promise<RbacPermissionRow | undefined>;
  deleteRbacPermission(id: number): Promise<boolean>;

  getLocalScans(repoId: number): Promise<LocalScan[]>;
  getLocalScan(id: number): Promise<LocalScan | undefined>;
  createLocalScan(data: InsertLocalScan): Promise<LocalScan>;

  getAuthProviders(): Promise<AuthProvider[]>;
  getAuthProvider(id: number): Promise<AuthProvider | undefined>;
  createAuthProvider(data: InsertAuthProvider): Promise<AuthProvider>;
  updateAuthProvider(id: number, data: Partial<InsertAuthProvider>): Promise<AuthProvider | undefined>;
  deleteAuthProvider(id: number): Promise<boolean>;

  getContainerScans(): Promise<ContainerScan[]>;
  createContainerScan(data: InsertContainerScan): Promise<ContainerScan>;

  getInfraScans(repoId: number): Promise<InfraScan[]>;
  createInfraScan(data: InsertInfraScan): Promise<InfraScan>;
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

  async getQualityScans(repoId: number) { return db.select().from(qualityScans).where(eq(qualityScans.repoConnectionId, repoId)); }
  async createQualityScan(data: InsertQualityScan) { const [s] = await db.insert(qualityScans).values(data).returning(); return s; }

  async getRbacPermissions() { return db.select().from(rbacPermissions); }
  async createRbacPermission(data: InsertRbacPermission) { const [p] = await db.insert(rbacPermissions).values(data).returning(); return p; }
  async updateRbacPermission(id: number, data: Partial<InsertRbacPermission>) { const [p] = await db.update(rbacPermissions).set(data).where(eq(rbacPermissions.id, id)).returning(); return p; }
  async deleteRbacPermission(id: number) { const result = await db.delete(rbacPermissions).where(eq(rbacPermissions.id, id)).returning(); return result.length > 0; }

  async getLocalScans(repoId: number) { return db.select().from(localScans).where(eq(localScans.repoConnectionId, repoId)); }
  async getLocalScan(id: number) { const [s] = await db.select().from(localScans).where(eq(localScans.id, id)); return s; }
  async createLocalScan(data: InsertLocalScan) { const [s] = await db.insert(localScans).values(data).returning(); return s; }

  async getAuthProviders() { return db.select().from(authProviders); }
  async getAuthProvider(id: number) { const [p] = await db.select().from(authProviders).where(eq(authProviders.id, id)); return p; }
  async createAuthProvider(data: InsertAuthProvider) { const [p] = await db.insert(authProviders).values(data).returning(); return p; }
  async deleteAuthProvider(id: number) { const result = await db.delete(authProviders).where(eq(authProviders.id, id)).returning(); return result.length > 0; }
  async updateAuthProvider(id: number, data: Partial<InsertAuthProvider>) { const [p] = await db.update(authProviders).set(data).where(eq(authProviders.id, id)).returning(); return p; }

  async getContainerScans() { return db.select().from(containerScans); }
  async createContainerScan(data: InsertContainerScan) { const [s] = await db.insert(containerScans).values(data).returning(); return s; }

  async getInfraScans(repoId: number) { return db.select().from(infraScans).where(eq(infraScans.repoConnectionId, repoId)); }
  async createInfraScan(data: InsertInfraScan) { const [s] = await db.insert(infraScans).values(data).returning(); return s; }
}

export const storage = new DatabaseStorage();
