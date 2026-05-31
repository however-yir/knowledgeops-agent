import { Injectable } from "@nestjs/common";

import { env } from "../config/env.js";
import { CourseRecord, CourseReservationRecord, PlatformStore, SchoolRecord } from "./platform.store.js";
import { MetricsService } from "./metrics.service.js";

type PrismaClientLike = Record<string, any> & {
  $connect?: () => Promise<void>;
};

interface CourseQuery {
  edu?: number;
  type?: string;
  sorts?: Array<{ field?: string; isAsc?: boolean }>;
}

const ALLOWED_SORT_FIELDS = new Set(["price", "duration", "edu", "id"]);

@Injectable()
export class BusinessToolsService {
  private prismaClient: PrismaClientLike | undefined;

  constructor(
    private readonly store: PlatformStore,
    private readonly metrics: MetricsService
  ) {}

  async querySchool(): Promise<SchoolRecord[]> {
    return this.instrument("query_school", async () => {
      const prisma = await this.prisma().catch(() => undefined);
      if (prisma?.school) {
        const rows = await prisma.school.findMany({ orderBy: { id: "asc" } });
        return rows.map((row: Record<string, unknown>) => ({
          id: Number(row.id),
          name: String(row.name ?? ""),
          city: row.city ? String(row.city) : undefined
        }));
      }
      return [...this.store.schools].sort((a, b) => a.id - b.id);
    });
  }

  async queryCourse(rawQuery?: CourseQuery): Promise<CourseRecord[]> {
    return this.instrument("query_course", async () => {
      const query = normalizeCourseQuery(rawQuery);
      const orderBy = query.sorts.length
        ? query.sorts.map((sort) => ({ [sort.field]: sort.isAsc ? "asc" : "desc" }))
        : [{ id: "asc" }];
      const prisma = await this.prisma().catch(() => undefined);
      if (prisma?.course) {
        const rows = await prisma.course.findMany({
          where: {
            ...(query.edu === undefined ? {} : { edu: { lte: query.edu } }),
            ...(query.type ? { type: query.type } : {})
          },
          orderBy
        });
        return rows.map((row: Record<string, unknown>) => ({
          id: Number(row.id),
          name: String(row.name ?? ""),
          edu: optionalNumber(row.edu),
          type: row.type ? String(row.type) : undefined,
          price: optionalNumber(row.price),
          duration: optionalNumber(row.duration)
        }));
      }
      return sortCourses(this.store.courses.filter((course) => {
        const eduOk = query.edu === undefined || course.edu === undefined || course.edu <= query.edu;
        const typeOk = !query.type || course.type === query.type;
        return eduOk && typeOk;
      }), query.sorts);
    });
  }

  async addCourseReservation(input: {
    course?: string;
    studentName?: string;
    contactInfo?: string;
    school?: string;
    remark?: string;
  }): Promise<{ status: "created"; reservationId: string }> {
    return this.instrument("add_course_reservation", async () => {
      const course = clean(input.course);
      const studentName = clean(input.studentName);
      const contactInfo = clean(input.contactInfo);
      const school = clean(input.school);
      if (!course || !studentName || !contactInfo || !school) {
        throw new Error("missing required fields for reservation");
      }
      const remark = clean(input.remark);
      const prisma = await this.prisma().catch(() => undefined);
      const created = prisma?.courseReservation
        ? await prisma.courseReservation.create({ data: { course, studentName, contactInfo, school, remark } })
        : undefined;
      const record: CourseReservationRecord = {
        id: created?.id === undefined ? nextReservationId(this.store.courseReservations) : Number(created.id),
        course,
        studentName,
        contactInfo,
        school,
        remark
      };
      this.store.courseReservations.push(record);
      this.store.persist();
      return { status: "created" as const, reservationId: String(record.id) };
    });
  }

  private async instrument<T>(tool: string, operation: () => Promise<T>): Promise<T> {
    const started = Date.now();
    try {
      const result = await operation();
      this.metrics.observe("tool_query_latency_ms", Date.now() - started, { tool, status: "success" });
      return result;
    } catch (error) {
      this.metrics.observe("tool_query_latency_ms", Date.now() - started, { tool, status: "error" });
      throw error;
    }
  }

  private async prisma(): Promise<PrismaClientLike | undefined> {
    if (!env.APP_PRISMA_ENABLED || !env.DATABASE_URL) {
      return undefined;
    }
    if (this.prismaClient) {
      return this.prismaClient;
    }
    const dynamicImport = new Function("specifier", "return import(specifier)") as (specifier: string) => Promise<{ PrismaClient: new () => PrismaClientLike }>;
    const module = await dynamicImport("@prisma/client");
    this.prismaClient = new module.PrismaClient();
    await this.prismaClient.$connect?.();
    return this.prismaClient;
  }
}

function normalizeCourseQuery(query?: CourseQuery): { edu?: number; type?: string; sorts: Array<{ field: string; isAsc: boolean }> } {
  return {
    edu: optionalNumber(query?.edu),
    type: clean(query?.type),
    sorts: (query?.sorts ?? [])
      .map((sort) => ({ field: clean(sort.field), isAsc: sort.isAsc !== false }))
      .filter((sort): sort is { field: string; isAsc: boolean } => Boolean(sort.field && ALLOWED_SORT_FIELDS.has(sort.field)))
  };
}

function sortCourses(courses: CourseRecord[], sorts: Array<{ field: string; isAsc: boolean }>): CourseRecord[] {
  const ordered = [...courses];
  if (sorts.length === 0) {
    return ordered.sort((a, b) => a.id - b.id);
  }
  return ordered.sort((a, b) => {
    for (const sort of sorts) {
      const left = valueForSort(a, sort.field);
      const right = valueForSort(b, sort.field);
      if (left === right) {
        continue;
      }
      return (left - right) * (sort.isAsc ? 1 : -1);
    }
    return a.id - b.id;
  });
}

function valueForSort(course: CourseRecord, field: string): number {
  const value = course[field as keyof CourseRecord];
  return typeof value === "number" ? value : Number.MAX_SAFE_INTEGER;
}

function optionalNumber(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") {
    return undefined;
  }
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : undefined;
}

function clean(value: unknown): string | undefined {
  const text = String(value ?? "").trim();
  return text || undefined;
}

function nextReservationId(records: CourseReservationRecord[]): number {
  return records.reduce((max, record) => Math.max(max, record.id), 0) + 1;
}
