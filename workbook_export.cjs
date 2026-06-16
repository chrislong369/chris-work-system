const fs = require("node:fs/promises");
const path = require("node:path");
const { SpreadsheetFile, Workbook } = require("@oai/artifact-tool");

const COLORS = {
  navy: "#17324D",
  blue: "#2F75B5",
  paleBlue: "#DCEAF7",
  green: "#548235",
  paleGreen: "#E2F0D9",
  gold: "#BF9000",
  paleGold: "#FFF2CC",
  red: "#C00000",
  paleRed: "#FCE4D6",
  border: "#D9E2F3",
  text: "#1F2937",
  white: "#FFFFFF",
};

function columnName(index) {
  let result = "";
  let value = index + 1;
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function setMatrix(sheet, startRow, startCol, matrix) {
  if (!matrix.length || !matrix[0].length) return;
  const endRow = startRow + matrix.length - 1;
  const endCol = startCol + matrix[0].length - 1;
  sheet.getRangeByIndexes(startRow, startCol, matrix.length, matrix[0].length).values = matrix;
  return sheet.getRange(`${columnName(startCol)}${startRow + 1}:${columnName(endCol)}${endRow + 1}`);
}

function styleHeader(range, fill = COLORS.navy) {
  range.format = {
    fill,
    font: { bold: true, color: COLORS.white },
    borders: { preset: "all", style: "thin", color: COLORS.border },
    verticalAlignment: "center",
    wrapText: true,
  };
}

function styleSection(range) {
  range.format = {
    fill: COLORS.paleBlue,
    font: { bold: true, color: COLORS.navy },
    borders: { preset: "all", style: "thin", color: COLORS.border },
  };
}

function formatDataSheet(sheet, headers, rows) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const rowCount = Math.max(rows.length + 1, 2);
  styleHeader(sheet.getRangeByIndexes(0, 0, 1, headers.length));
  const currencyHeaders = new Set(["default_rate", "rate", "amount"]);
  const numberHeaders = new Set(["quantity"]);
  for (let col = 0; col < headers.length; col += 1) {
    const values = [headers[col], ...rows.map((row) => String(row[col] ?? ""))];
    const longest = Math.max(...values.map((value) => value.length));
    const width = Math.max(11, Math.min(38, longest + 2));
    const columnRange = sheet.getRangeByIndexes(0, col, rowCount, 1);
    columnRange.format.columnWidth = width;
    if (currencyHeaders.has(headers[col])) {
      sheet.getRangeByIndexes(1, col, rowCount - 1, 1).format.numberFormat = "$#,##0.00;[Red]-$#,##0.00";
    } else if (numberHeaders.has(headers[col])) {
      sheet.getRangeByIndexes(1, col, rowCount - 1, 1).format.numberFormat = "0.00";
    } else if (headers[col].endsWith("_at")) {
      sheet.getRangeByIndexes(1, col, rowCount - 1, 1).format.numberFormat = "yyyy-mm-dd hh:mm";
    } else if (headers[col] === "date" || headers[col].endsWith("_date")) {
      sheet.getRangeByIndexes(1, col, rowCount - 1, 1).format.numberFormat = "yyyy-mm-dd";
    }
  }
  const used = sheet.getRangeByIndexes(0, 0, rows.length + 1, headers.length);
  used.format.borders = { preset: "all", style: "thin", color: COLORS.border };
  if (rows.length) {
    const table = sheet.tables.add(
      `A1:${columnName(headers.length - 1)}${rows.length + 1}`,
      true,
      `${sheet.name.replace(/[^A-Za-z0-9]/g, "")}Table`,
    );
    table.style = "TableStyleMedium2";
    table.showBandedRows = true;
  }
}

function addDashboard(workbook, dashboard) {
  const sheet = workbook.worksheets.add("Dashboard");
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(2);
  sheet.mergeCells("A1:H1");
  sheet.getRange("A1").values = [[`Chris Work System Dashboard - ${dashboard.as_of}`]];
  sheet.getRange("A1:H1").format = {
    fill: COLORS.navy,
    font: { bold: true, color: COLORS.white, size: 18 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
  sheet.getRange("A1:H1").format.rowHeight = 30;

  setMatrix(sheet, 2, 0, [["Key Metric", "Value"]]);
  styleHeader(sheet.getRange("A3:B3"), COLORS.blue);
  const kpiRows = dashboard.kpis.map(([label, value]) => [label, value]);
  setMatrix(sheet, 3, 0, kpiRows);
  sheet.getRange(`A4:B${3 + kpiRows.length}`).format.borders = {
    preset: "all", style: "thin", color: COLORS.border,
  };
  dashboard.kpis.forEach((entry, index) => {
    const cell = sheet.getRange(`B${index + 4}`);
    if (entry[2] === "currency") cell.format.numberFormat = "$#,##0.00;[Red]-$#,##0.00";
    if (entry[2] === "number") cell.format.numberFormat = "0.00";
    if (entry[2] === "integer") cell.format.numberFormat = "0";
  });

  setMatrix(sheet, 2, 3, [["Money Owed By Customer", "Amount"], ...dashboard.owed_by_customer]);
  styleHeader(sheet.getRange(`D3:E3`), COLORS.green);
  if (dashboard.owed_by_customer.length) {
    sheet.getRange(`E4:E${3 + dashboard.owed_by_customer.length}`).format.numberFormat = "$#,##0.00;[Red]-$#,##0.00";
  }

  setMatrix(sheet, 2, 6, [["Money Owed By Job", "Amount"], ...dashboard.owed_by_job]);
  styleHeader(sheet.getRange("G3:H3"), COLORS.gold);
  if (dashboard.owed_by_job.length) {
    sheet.getRange(`H4:H${3 + dashboard.owed_by_job.length}`).format.numberFormat = "$#,##0.00;[Red]-$#,##0.00";
  }

  const summaryBottom = Math.max(
    3 + dashboard.kpis.length,
    3 + dashboard.owed_by_customer.length,
    3 + dashboard.owed_by_job.length,
  );
  const hoursStart = summaryBottom + 2;
  setMatrix(sheet, hoursStart - 1, 0, [["Hours Worked By Customer", "Hours"], ...dashboard.hours_by_customer]);
  styleSection(sheet.getRange(`A${hoursStart}:B${hoursStart}`));
  if (dashboard.hours_by_customer.length) {
    sheet.getRange(`B${hoursStart + 1}:B${hoursStart + dashboard.hours_by_customer.length}`).format.numberFormat = "0.00";
  }

  const tasksStart = hoursStart;
  setMatrix(sheet, tasksStart - 1, 3, [["Open Tasks", "Job", "Task", "Due Date", "Status"], ...dashboard.open_tasks]);
  styleSection(sheet.getRange(`D${tasksStart}:H${tasksStart}`));

  const detailStart = Math.max(
    hoursStart + dashboard.hours_by_customer.length + 2,
    tasksStart + dashboard.open_tasks.length + 2,
  );
  setMatrix(sheet, detailStart - 1, 0, [
    ["Outstanding / Unscheduled Jobs", "Task Description", "Status", "Priority", "Next Action", "Due / Timing", "Last Updated", "Notes"],
    ...dashboard.outstanding_backlog,
  ]);
  styleSection(sheet.getRange(`A${detailStart}:H${detailStart}`));

  const upcomingStart = detailStart + dashboard.outstanding_backlog.length + 3;
  setMatrix(sheet, upcomingStart - 1, 0, [
    ["Upcoming Scheduled Jobs", "Start", "End", "Customer", "Title", "Location", "Status"],
    ...dashboard.upcoming,
  ]);
  styleSection(sheet.getRange(`A${upcomingStart}:G${upcomingStart}`));

  const reviewStart = upcomingStart + dashboard.upcoming.length + 3;
  setMatrix(sheet, reviewStart - 1, 0, [
    ["Raw Updates Needing Review", "Customer", "Type", "Validation Errors"],
    ...dashboard.review_rows,
  ]);
  styleHeader(sheet.getRange(`A${reviewStart}:D${reviewStart}`), COLORS.red);

  const widths = [30, 38, 16, 14, 34, 22, 22, 38];
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, Math.max(reviewStart + dashboard.review_rows.length, 20), 1).format.columnWidth = width;
  });
  sheet.getRange(`A3:H${Math.max(reviewStart + dashboard.review_rows.length, 20)}`).format.borders = {
    preset: "all", style: "thin", color: COLORS.border,
  };

  if (dashboard.owed_by_customer.length) {
    const chart = sheet.charts.add("bar", sheet.getRange(`D3:E${3 + dashboard.owed_by_customer.length}`));
    chart.title = "Money Owed By Customer";
    chart.hasLegend = false;
    chart.yAxis = { numberFormatCode: "$#,##0" };
    chart.setPosition("J2", "Q18");
  }
  return sheet;
}

async function main() {
  const [snapshotPath, outputPath, previewDir] = process.argv.slice(2);
  if (!snapshotPath || !outputPath) {
    throw new Error("Usage: node workbook_export.cjs <snapshot.json> <output.xlsx> [preview_dir]");
  }
  const payload = JSON.parse(await fs.readFile(snapshotPath, "utf8"));
  const workbook = Workbook.create();
  addDashboard(workbook, payload.dashboard);

  for (const source of payload.sheets) {
    const sheet = workbook.worksheets.add(source.name);
    setMatrix(sheet, 0, 0, [source.headers, ...source.rows]);
    formatDataSheet(sheet, source.headers, source.rows);
  }

  if (previewDir) {
    await fs.mkdir(previewDir, { recursive: true });
    for (const sheet of workbook.worksheets.items) {
      const preview = await workbook.render({
        sheetName: sheet.name,
        autoCrop: "all",
        scale: 1,
        format: "png",
      });
      await fs.writeFile(
        path.join(previewDir, `${sheet.name.replace(/[^A-Za-z0-9]+/g, "_")}.png`),
        new Uint8Array(await preview.arrayBuffer()),
      );
    }
  }

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
  console.log(`Created ${outputPath}`);
}

main().catch((error) => {
  console.error(error.stack || error.message || error);
  process.exit(1);
});
