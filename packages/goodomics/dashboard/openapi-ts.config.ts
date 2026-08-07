import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../../../openapi/goodomics.openapi.json",
  output: {
    path: "src/api/generated",
  },
  plugins: [
    "@hey-api/client-fetch",
    "@hey-api/typescript",
    {
      name: "@hey-api/sdk",
      operations: "flat",
      paramsStructure: "grouped",
      responseStyle: "data",
      validator: { request: false, response: "zod" },
    },
    {
      name: "zod",
      compatibilityVersion: 4,
    },
  ],
});
