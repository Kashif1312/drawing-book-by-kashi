# =============================================================================
#  Drawing Book Web App
#  Stack : Streamlit + streamlit-drawable-canvas + Pillow
#  Deploy: Streamlit Community Cloud  (streamlit.io/cloud)
# =============================================================================

import io
import copy

import numpy as np
import streamlit as st
from PIL import Image
from streamlit_drawable_canvas import st_canvas

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Drawing Book",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ----- fonts & base ----- */
    html, body, [class*="css"] {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }

    /* ----- sidebar background ----- */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
        min-width: 270px;
    }
    [data-testid="stSidebar"] * { color: #e0e0e0 !important; }

    /* ----- sidebar buttons ----- */
    [data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(135deg, #0f3460, #533483);
        color: #fff !important;
        border: none;
        border-radius: 8px;
        width: 100%;
        padding: 7px 10px;
        margin: 2px 0;
        font-size: 13px;
        font-weight: 600;
        transition: all .2s ease;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: linear-gradient(135deg, #533483, #e94560);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(233,69,96,.4);
    }

    /* ----- section labels ----- */
    .section-label {
        background: rgba(255,255,255,.07);
        border-left: 3px solid #e94560;
        border-radius: 5px;
        padding: 5px 10px;
        margin: 10px 0 4px 0;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        color: #e94560 !important;
    }

    /* ----- canvas wrapper ----- */
    .canvas-wrap {
        background: #dde;
        border-radius: 12px;
        padding: 10px;
        box-shadow: 0 8px 30px rgba(0,0,0,.2);
    }

    /* ----- status strip ----- */
    .status-strip {
        background: #1a1a2e;
        color: #888;
        padding: 4px 14px;
        border-radius: 0 0 8px 8px;
        font-size: 11px;
    }

    /* ----- main header ----- */
    .main-header {
        background: linear-gradient(90deg, #1a1a2e, #0f3460);
        padding: 13px 20px;
        border-radius: 12px;
        margin-bottom: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Keyboard shortcuts (JS → clicks our Streamlit buttons) ───────────────────
# We rely on data-testid attributes to locate the hidden trigger checkboxes
# and call .click() when the shortcut fires.  The checkboxes themselves are
# rendered in the main area below as zero-height containers.
st.markdown(
    """
    <script>
    (function () {
        if (window.__dbShortcuts) return;
        window.__dbShortcuts = true;
        document.addEventListener('keydown', function (e) {
            if (!(e.ctrlKey || e.metaKey)) return;
            var key = e.key.toLowerCase();
            var map = { z: 'kb-undo', x: 'kb-redo', s: 'kb-save' };
            if (map[key]) {
                e.preventDefault();
                var el = document.querySelector('[data-testid="' + map[key] + '"] input');
                if (el) el.click();
            }
        });
    })();
    </script>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
#  SESSION STATE
# =============================================================================

def _init():
    defaults = {
        # history
        "undo_stack":    [],
        "redo_stack":    [],
        "canvas_json":   None,
        # tool
        "tool":          "freedraw",
        "shape":         "rect",
        "text_content":  "Hello!",
        # colours
        "stroke_hex":    "#000000",
        "fill_hex":      "#ffffff",
        "bg_hex":        "#ffffff",
        # brush
        "thickness":     4,
        "opacity":       1.0,
        # canvas size
        "cv_w":          880,
        "cv_h":          560,
        "zoom_label":    "100%",
        # pages
        "page_no":       1,
        "page_total":    1,
        "pages":         {1: None},
        # misc
        "ck":            0,      # canvas key – increment forces reset
        "saved_pil":     None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()
S = st.session_state   # short alias


# =============================================================================
#  HELPERS
# =============================================================================

def _push_undo(j):
    if j:
        S.undo_stack.append(copy.deepcopy(j))
        S.redo_stack.clear()


def _do_undo():
    if S.undo_stack:
        S.redo_stack.append(copy.deepcopy(S.canvas_json))
        S.canvas_json = S.undo_stack.pop()
        S.ck += 1


def _do_redo():
    if S.redo_stack:
        S.undo_stack.append(copy.deepcopy(S.canvas_json))
        S.canvas_json = S.redo_stack.pop()
        S.ck += 1


def _clear():
    _push_undo(S.canvas_json)
    S.canvas_json = None
    S.ck += 1


def _add_page():
    S.pages[S.page_no] = S.canvas_json
    S.page_total += 1
    new = S.page_total
    S.pages[new] = None
    S.page_no = new
    S.canvas_json = None
    S.ck += 1


def _del_page():
    if S.page_total == 1:
        return
    del S.pages[S.page_no]
    S.page_total -= 1
    S.pages = {i + 1: v for i, v in enumerate(S.pages.values())}
    S.page_no = min(S.page_no, S.page_total)
    S.canvas_json = S.pages.get(S.page_no)
    S.ck += 1


def _switch_page(n):
    if n == S.page_no:
        return
    S.pages[S.page_no] = S.canvas_json
    S.page_no = n
    S.canvas_json = S.pages.get(n)
    S.ck += 1


def _canvas_to_pil(result, w, h):
    if result is not None and result.image_data is not None:
        arr = result.image_data.astype(np.uint8)
        return Image.fromarray(arr, "RGBA")
    return Image.new("RGBA", (w, h), (255, 255, 255, 255))


def _pil_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _zoom_factor(label):
    return {"100%": 1.0, "125%": 1.25, "150%": 1.5, "200%": 2.0}.get(label, 1.0)


def _drawing_mode():
    """Map our tool + shape to streamlit-drawable-canvas drawing_mode."""
    t = S.tool
    if t == "freedraw":
        return "freedraw"
    if t == "eraser":
        return "freedraw"
    if t == "text":
        return "point"        # user clicks; we stamp text via initial_drawing
    if t == "shape":
        return {
            "line":     "line",
            "rect":     "rect",
            "circle":   "circle",
            "triangle": "polygon",
            "polygon":  "polygon",
        }.get(S.shape, "rect")
    return "freedraw"


def _stroke_color():
    """Eraser paints with background colour."""
    return S.bg_hex if S.tool == "eraser" else S.stroke_hex


# =============================================================================
#  SIDEBAR
# =============================================================================

with st.sidebar:

    st.markdown("## 🎨 Drawing Book")
    st.markdown("---")

    # ── Pages ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">📄 Pages</div>', unsafe_allow_html=True)

    col_ins, col_del = st.columns(2)
    with col_ins:
        if st.button("➕ New Page", use_container_width=True):
            _add_page()
            st.rerun()
    with col_del:
        if st.button("🗑️ Delete", use_container_width=True):
            _del_page()
            st.rerun()

    page_choice = st.selectbox(
        f"Page  ({S.page_total} total)",
        options=list(S.pages.keys()),
        index=S.page_no - 1,
        format_func=lambda n: f"Page {n}",
    )
    if page_choice != S.page_no:
        _switch_page(page_choice)
        st.rerun()

    # ── Edit actions ────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">⚙️ Edit</div>', unsafe_allow_html=True)

    col_u, col_r = st.columns(2)
    with col_u:
        if st.button("↩ Undo", use_container_width=True, help="Ctrl + Z"):
            _do_undo()
            st.rerun()
    with col_r:
        if st.button("↪ Redo", use_container_width=True, help="Ctrl + X"):
            _do_redo()
            st.rerun()

    col_cl, col_sv = st.columns(2)
    with col_cl:
        if st.button("🗑 Clear", use_container_width=True):
            _clear()
            st.rerun()
    with col_sv:
        if st.button("💾 Save", use_container_width=True, help="Ctrl + S"):
            S.saved_pil = "pending"

    # ── Tool box ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">🛠️ Tools</div>', unsafe_allow_html=True)

    TOOLS = [
        ("✏️  Pencil",  "freedraw"),
        ("🖊  Eraser",  "eraser"),
        ("📝  Text",    "text"),
        ("🔷  Shapes",  "shape"),
        ("🪣  Fill",    "fill"),
    ]
    for label, key in TOOLS:
        prefix = "✅ " if S.tool == key else "    "
        if st.button(f"{prefix}{label}", key=f"tool_{key}", use_container_width=True):
            S.tool = key
            st.rerun()

    if S.tool == "text":
        S.text_content = st.text_input("Text to stamp:", value=S.text_content)

    # ── Shapes ──────────────────────────────────────────────────────────────
    if S.tool == "shape":
        st.markdown('<div class="section-label">🔷 Shape</div>', unsafe_allow_html=True)
        SHAPE_OPTIONS = {
            "── Line":       "line",
            "▭  Rectangle":  "rect",
            "○  Circle":     "circle",
            "△  Triangle":   "triangle",
            "⬡  Polygon":    "polygon",
        }
        picked = st.radio(
            "Pick shape",
            list(SHAPE_OPTIONS.keys()),
            index=list(SHAPE_OPTIONS.values()).index(S.shape),
            label_visibility="collapsed",
        )
        S.shape = SHAPE_OPTIONS[picked]

    # ── Brush settings ──────────────────────────────────────────────────────
    st.markdown('<div class="section-label">🖌️ Brush</div>', unsafe_allow_html=True)

    S.thickness = st.slider("Thickness", 1, 80, S.thickness)
    st.slider("Strength (visual)", 1, 10, 5, help="Cosmetic weight indicator")
    S.opacity = st.select_slider(
        "Opacity",
        options=[0.2, 0.4, 0.6, 0.8, 1.0],
        value=S.opacity,
        format_func=lambda x: f"{int(x * 100)}%",
    )

    # ── Color palette ───────────────────────────────────────────────────────
    st.markdown('<div class="section-label">🎨 Colors</div>', unsafe_allow_html=True)

    PRESET = [
        ("#000000", "⬛"), ("#ffffff", "⬜"), ("#e74c3c", "🟥"), ("#3498db", "🟦"),
        ("#2ecc71", "🟩"), ("#f39c12", "🟧"), ("#9b59b6", "🟪"), ("#1abc9c", "🟩"),
    ]
    cols_p = st.columns(8)
    for idx, (hex_c, icon) in enumerate(PRESET):
        with cols_p[idx]:
            if st.button(icon, key=f"preset_{idx}", help=hex_c):
                S.stroke_hex = hex_c
                st.rerun()

    S.stroke_hex = st.color_picker("Stroke colour", S.stroke_hex)
    S.fill_hex   = st.color_picker("Fill colour",   S.fill_hex)
    S.bg_hex     = st.color_picker("Background",    S.bg_hex)

    # ── Canvas dimensions ───────────────────────────────────────────────────
    st.markdown('<div class="section-label">📐 Canvas Size</div>', unsafe_allow_html=True)
    S.cv_w = st.slider("Width (px)",  400, 1400, S.cv_w, step=40)
    S.cv_h = st.slider("Height (px)", 300, 1000, S.cv_h, step=40)

    # ── Download ─────────────────────────────────────────────────────────────
    st.markdown("---")
    if S.saved_pil and S.saved_pil != "pending":
        st.download_button(
            label="⬇️  Download PNG",
            data=_pil_to_bytes(S.saved_pil),
            file_name=f"drawing_page{S.page_no}.png",
            mime="image/png",
            use_container_width=True,
        )

    st.markdown(
        "<div style='font-size:10px;color:#555;text-align:center;margin-top:8px;'>"
        "Ctrl+Z Undo · Ctrl+X Redo · Ctrl+S Save"
        "</div>",
        unsafe_allow_html=True,
    )


# =============================================================================
#  MAIN AREA
# =============================================================================

# Header
st.markdown(
    """
    <div class="main-header">
      <span style="font-size:26px;">🎨</span>
      <span style="color:#fff;font-size:20px;font-weight:700;margin-left:10px;">
        Drawing Book
      </span>
      <span style="color:#aaa;font-size:13px;margin-left:14px;">
        Professional Drawing Studio
      </span>
    </div>
    """,
    unsafe_allow_html=True,
)

# Top row: info strip + zoom
info_col, zoom_col = st.columns([5, 1])

with zoom_col:
    S.zoom_label = st.radio(
        "🔍 Zoom",
        ["100%", "125%", "150%", "200%"],
        index=["100%", "125%", "150%", "200%"].index(S.zoom_label),
    )

zoom = _zoom_factor(S.zoom_label)
eff_w = int(S.cv_w * zoom)
eff_h = int(S.cv_h * zoom)

with info_col:
    obj_count = 0
    if S.canvas_json and S.canvas_json.get("objects"):
        obj_count = len(S.canvas_json["objects"])

    st.markdown(
        "<div style='background:#e8e8e8;padding:4px 12px;"
        "border-radius:8px 8px 0 0;font-size:12px;color:#444;'>"
        f"📄 Page <b>{S.page_no}</b> of <b>{S.page_total}</b> &nbsp;|&nbsp; "
        f"Tool: <b>{S.tool}</b> &nbsp;|&nbsp; "
        f"Objects: <b>{obj_count}</b> &nbsp;|&nbsp; "
        f"Zoom: <b>{S.zoom_label}</b> &nbsp;|&nbsp; "
        f"Canvas: <b>{S.cv_w}×{S.cv_h}</b> px"
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Canvas ───────────────────────────────────────────────────────────────
    result = st_canvas(
        fill_color=S.fill_hex,
        stroke_width=S.thickness,
        stroke_color=_stroke_color(),
        background_color=S.bg_hex,
        update_streamlit=True,
        height=eff_h,
        width=eff_w,
        drawing_mode=_drawing_mode(),
        display_toolbar=False,
        initial_drawing=S.canvas_json,
        key=f"canvas_{S.ck}",
    )

    # Status strip
    st.markdown(
        "<div class='status-strip'>"
        f"Undo stack: {len(S.undo_stack)} &nbsp;|&nbsp; "
        f"Redo stack: {len(S.redo_stack)} &nbsp;|&nbsp; "
        f"Opacity: {int(S.opacity * 100)}% &nbsp;|&nbsp; "
        f"Thickness: {S.thickness}px"
        "</div>",
        unsafe_allow_html=True,
    )


# =============================================================================
#  PROCESS CANVAS RESULT
# =============================================================================

if result.json_data is not None:
    new_json = result.json_data

    # Only push to undo when something was actually drawn
    if new_json != S.canvas_json and new_json.get("objects"):
        _push_undo(S.canvas_json)
        S.canvas_json = new_json
        S.pages[S.page_no] = new_json

    # ── Text tool: stamp text object at clicked point ─────────────────────
    if (
        S.tool == "text"
        and S.text_content.strip()
        and new_json.get("objects")
    ):
        last = new_json["objects"][-1]
        # A "point" click creates a tiny circle — detect it and replace with text
        if last.get("type") == "circle" and last.get("radius", 99) < 5:
            x = float(last.get("left", 50))
            y = float(last.get("top", 50))
            text_obj = {
                "type": "textbox",
                "version": "5.2.1",
                "originX": "left",
                "originY": "top",
                "left": x,
                "top": y,
                "width": 300,
                "fill": S.stroke_hex,
                "text": S.text_content,
                "fontSize": max(14, S.thickness * 3),
                "fontFamily": "Arial",
                "fontWeight": "normal",
                "opacity": S.opacity,
            }
            base = S.canvas_json or {"objects": []}
            objects = [o for o in base.get("objects", [])
                       if not (o.get("type") == "circle" and o.get("radius", 99) < 5)]
            objects.append(text_obj)
            base["objects"] = objects
            _push_undo(S.canvas_json)
            S.canvas_json = base
            S.pages[S.page_no] = base
            S.ck += 1
            st.rerun()


# ── Handle save signal ────────────────────────────────────────────────────────
if S.saved_pil == "pending":
    S.saved_pil = _canvas_to_pil(result, eff_w, eff_h)
    st.success("✅ Canvas saved — use **Download PNG** in the sidebar.")
    st.rerun()


# =============================================================================
#  SHORTCUTS HELP
# =============================================================================

with st.expander("⌨️  Keyboard Shortcuts", expanded=False):
    st.markdown(
        """
| Shortcut | Action |
|---|---|
| `Ctrl + Z` | Undo last stroke |
| `Ctrl + X` | Redo |
| `Ctrl + S` | Save canvas to memory |
| Sidebar → **Download PNG** | Export current page |
        """
    )

# Footer
st.markdown(
    "<div style='text-align:center;color:#555;font-size:11px;"
    "margin-top:18px;padding-top:8px;border-top:1px solid #333;'>"
    "🎨 Drawing Book &nbsp;·&nbsp; "
    "Built with Streamlit &amp; streamlit-drawable-canvas"
    "</div>",
    unsafe_allow_html=True,
)
