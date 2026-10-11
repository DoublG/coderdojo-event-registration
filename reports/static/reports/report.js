// A report page (DATA_MODEL_REPORTS.md §30): Perspective's viewer on one
// reporting dataset. Loaded as a module on the report pages only, which are
// also the only pages whose Content-Security-Policy allows WebAssembly
// (reports.views.perspective_policy). The figures come from the dataset's
// endpoint; the saved settings from the page (#report-setup), already in the
// page's language (reports.config). Saving puts viewer.save() in the form's
// hidden `config` field and lets the form post as usual.
//
// The bundles start their WebAssembly glue and the chart plugin's renderer
// from blob: URLs (in the page and inside a worker), so these pages' policy
// also allows blob: in script-src and worker-src; a blocked import inside a
// worker fails silently, as an empty chart.
import perspective from "./vendor/perspective-5.5.1/client/dist/cdn/perspective.js";
import "./vendor/perspective-5.5.1/viewer/dist/cdn/perspective-viewer.js";
import "./vendor/perspective-5.5.1/viewer-datagrid/dist/cdn/perspective-viewer-datagrid.js";
import "./vendor/perspective-5.5.1/viewer-charts/dist/cdn/perspective-viewer-charts.js";

const viewer = document.getElementById("report-viewer");
const setupNode = document.getElementById("report-setup");

function showError(message) {
  const note = document.getElementById("report-error");
  if (note) {
    note.textContent = message;
    note.hidden = false;
  }
}

async function start() {
  if (!viewer || !setupNode) return;
  const setup = JSON.parse(setupNode.textContent);
  try {
    const response = await fetch(viewer.dataset.source, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const figures = await response.json();
    const worker = await perspective.worker();
    // An empty dataset still needs its columns, or the viewer has nothing to show.
    await worker.table(figures.rows.length ? figures.rows : setup.schema, { name: "figures" });
    await viewer.load(worker);
    await viewer.restore({
      ...setup.config,
      table: "figures",
      title: setup.title,
      theme: setup.dark ? "Pro Dark" : "Pro Light",
      settings: setup.editable && Object.keys(setup.config).length === 0,
    });
  } catch (error) {
    console.error(error);
    showError(setup.messages.loadFailed);
    return;
  }

  const form = document.getElementById("report-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const config = await viewer.save();
      form.querySelector("input[name=config]").value = JSON.stringify(config);
      // form.submit() sends no submit event and leaves out the button that
      // was clicked ("Save as a new report"), so that goes along by hand.
      const button = event.submitter;
      if (button && button.name) {
        const field = document.createElement("input");
        field.type = "hidden";
        field.name = button.name;
        field.value = button.value;
        form.append(field);
      }
      form.submit();
    });
  }
}

start();
