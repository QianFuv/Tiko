import { revalidatePath } from "next/cache";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactElement } from "react";

import { getApiBaseUrl } from "@/lib/api-client";
import type { DatasetRecord } from "@/lib/types";

type DatasetUploadSource = "csv" | "parquet";

/**
 * Render the dataset upload route.
 *
 * @returns Dataset upload page.
 */
export default function DatasetUploadPage(): ReactElement {
  return (
    <main className="min-h-screen bg-[#f4f6f8] text-[#17201b]">
      <section className="border-b border-[#d8dee4] bg-white">
        <div className="mx-auto max-w-4xl px-5 py-6 lg:px-8">
          <Link
            href="/datasets"
            className="text-sm font-medium text-[#1f6f8b] hover:text-[#174f63]"
          >
            Datasets
          </Link>
          <h1 className="mt-2 text-3xl font-semibold">Upload Dataset</h1>
        </div>
      </section>

      <section className="mx-auto max-w-4xl px-5 py-6 lg:px-8">
        <form
          action={uploadDataset}
          className="grid gap-5 rounded-lg border border-[#d8dee4] bg-white p-5"
        >
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Name
            <input
              name="name"
              required
              minLength={1}
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            File
            <input
              name="file"
              type="file"
              required
              accept=".csv,.parquet,.pq,text/csv,application/vnd.apache.parquet,application/octet-stream"
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            />
          </label>
          <label className="grid gap-2 text-sm font-medium text-[#17201b]">
            Source
            <select
              name="source"
              defaultValue=""
              className="rounded-md border border-[#cbd4dc] px-3 py-2 text-sm font-normal text-[#17201b] outline-none focus:border-[#1f6f8b]"
            >
              <option value="">Auto</option>
              <option value="csv">CSV</option>
              <option value="parquet">Parquet</option>
            </select>
          </label>
          <div className="flex justify-end">
            <button
              type="submit"
              className="rounded-md bg-[#1f6f8b] px-4 py-2 text-sm font-semibold text-white hover:bg-[#174f63]"
            >
              Upload
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}

/**
 * Upload a server-local dataset through the backend API.
 *
 * @param formData - Submitted dataset upload fields.
 */
async function uploadDataset(formData: FormData): Promise<void> {
  "use server";

  const payload = buildDatasetUploadFormData(formData);
  const response = await fetch(`${getApiBaseUrl()}/api/datasets/upload-file`, {
    method: "POST",
    headers: {
      "X-Tiko-Role": "admin",
      "X-Tiko-User": "frontend@app.local",
    },
    body: payload,
  });
  if (!response.ok) {
    throw new Error(
      `Dataset upload failed: ${await readErrorDetail(response)}`,
    );
  }
  const dataset = (await response.json()) as DatasetRecord;
  revalidatePath("/datasets");
  redirect(`/datasets/${dataset.dataset_id}`);
}

/**
 * Build a backend multipart dataset upload payload from form data.
 *
 * @param formData - Submitted form data.
 * @returns Dataset upload form data.
 */
function buildDatasetUploadFormData(formData: FormData): FormData {
  const name = readRequiredFormValue(formData, "name");
  const file = readRequiredFile(formData, "file");
  const source = readOptionalDatasetSource(formData);
  const payload = new FormData();
  payload.set("name", name);
  payload.set("file", file, file.name);
  if (source !== null) {
    payload.set("source", source);
  }
  return payload;
}

/**
 * Read a required uploaded file from form data.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Uploaded file.
 */
function readRequiredFile(formData: FormData, key: string): File {
  const value = formData.get(key);
  if (!(value instanceof File) || value.size === 0) {
    throw new Error(`${key} is required.`);
  }
  return value;
}

/**
 * Read an optional dataset source from submitted form data.
 *
 * @param formData - Submitted form data.
 * @returns Dataset source or null when auto-detecting.
 */
function readOptionalDatasetSource(
  formData: FormData,
): DatasetUploadSource | null {
  const value = String(formData.get("source") ?? "");
  if (value === "csv" || value === "parquet") {
    return value;
  }
  return null;
}

/**
 * Read a required string field from form data.
 *
 * @param formData - Submitted form data.
 * @param key - Field key.
 * @returns Trimmed field value.
 */
function readRequiredFormValue(formData: FormData, key: string): string {
  const value = formData.get(key);
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${key} is required.`);
  }
  return value.trim();
}

/**
 * Read a concise backend error detail from a failed response.
 *
 * @param response - Failed backend response.
 * @returns Backend error detail.
 */
async function readErrorDetail(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: unknown;
  } | null;
  if (typeof payload?.detail === "string") {
    return payload.detail;
  }
  return `HTTP ${response.status}`;
}
