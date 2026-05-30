export interface Result<T> {
  ok: 0 | 1;
  data?: T;
  message?: string;
}

export interface ApiHealth {
  status: "UP" | "DOWN";
}

export function ok<T>(data: T): Result<T> {
  return {
    ok: 1,
    data
  };
}

export function fail(message: string): Result<never> {
  return {
    ok: 0,
    message
  };
}
