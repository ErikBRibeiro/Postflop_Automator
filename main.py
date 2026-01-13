"""
Desktop Postflop automator (Board grid detection + robust OOP option selection)

Use case:
- You manually keep 2 fixed cards selected (any suit rows).
- Script cycles a third card across one suit row (A..2), keeping the fixed cards selected.
- No reliance on card templates (selected state can change appearance).

Board selection:
- Anchors on the main panel "Board" title via template.
- Crops a region below it where the 4 suit rows exist.
- Uses OpenCV to detect card rectangles (borders), independent of fill color (yellow selection).
- Sorts rectangles into 4 rows x 13 columns and clicks the target cell center.

OOP selection in Results:
- Locates the OOP panel box using two possible templates:
  - oop_panel_box_big.png (when nothing is selected yet)
  - oop_panel_box_small.png (after an option is selected)
- Clicks row 1, screenshot, row 2, screenshot, row 3, screenshot.
- Click points are computed proportionally inside the located panel box, so it works in both sizes.

Dependencies (Windows):
pip install pyautogui opencv-python pillow numpy pygetwindow

Templates needed in ./templates:
Board navigation and solver:
- panel_board_title.png      (crop of the "Board" title in the MAIN panel)
- menu_run_solver.png
- btn_build_new_tree.png
- btn_run_solver.png
- solver_finished.png
- top_results.png
- top_solver.png
- menu_board.png             (optional best-effort)

OOP panel (Results):
- oop_panel_box_big.png      (OOP panel when nothing selected; like your image 1)
- oop_panel_box_small.png    (OOP panel after selection; like your image 2)
"""

import os
import time
import datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple, List, Any

import numpy as np
import pyautogui
import cv2
from PIL import ImageGrab

try:
    import pygetwindow as gw
except Exception:
    gw = None


@dataclass
class Config:
    app_window_title_contains: str = "Desktop Postflop"
    templates_dir: str = "templates"
    output_root: str = "screenshots"

    # Template matching
    confidence: float = 0.85
    locate_timeout_sec: float = 30.0
    poll_interval_sec: float = 0.35

    # UI timings
    after_click_sleep_sec: float = 0.18
    after_navigation_sleep_sec: float = 0.55
    after_solver_start_sleep_sec: float = 1.0

    # Board grid crop relative to the "Board" title in main panel
    # You may tweak these once if needed.
    grid_offset_x: int = -10
    grid_offset_y: int = 45
    grid_width: int = 980
    grid_height: int = 330

    # Card rectangle detection constraints (in cropped grid coordinates)
    min_card_w: int = 35
    max_card_w: int = 120
    min_card_h: int = 45
    max_card_h: int = 140

    # Cycle behavior
    ranks_in_order: List[str] = None
    suit_row_to_cycle: str = "S"  # "S", "H", "D", "C" (row order assumed S,H,D,C top->bottom)
    deselect_previous_cycle_card: bool = True

    # If detection fails, retry how many times
    grid_detect_retries: int = 3

    # OOP panel click behavior
    oop_click_x_ratio: float = 0.12       # click near colored square area (left side inside panel)
    oop_header_ratio: float = 0.28        # portion for the "OOP" header area
    oop_rows: int = 3


CFG = Config(
    ranks_in_order=["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"],
    suit_row_to_cycle="S",
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


def ts() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def focus_app_window(title_contains: str) -> None:
    if gw is None:
        return
    wins = [w for w in gw.getAllWindows() if title_contains.lower() in (w.title or "").lower()]
    if not wins:
        return
    w = wins[0]
    try:
        if w.isMinimized:
            w.restore()
        w.activate()
        time.sleep(0.4)
    except Exception:
        pass


def template_path(name: str) -> str:
    p = os.path.join(CFG.templates_dir, name)
    if not os.path.exists(p):
        raise FileNotFoundError(f"Missing template: {p}")
    return p


def locate_center(template_file: str, timeout_sec: Optional[float] = None) -> Tuple[int, int, Any]:
    timeout = CFG.locate_timeout_sec if timeout_sec is None else timeout_sec
    start = time.time()
    last_err = None
    while time.time() - start <= timeout:
        try:
            box = pyautogui.locateOnScreen(template_file, confidence=CFG.confidence)
            if box is not None:
                c = pyautogui.center(box)
                return c.x, c.y, box
        except Exception as e:
            last_err = e
        time.sleep(CFG.poll_interval_sec)
    raise TimeoutError(f"Could not locate on screen: {template_file}. Last error: {last_err}")


def click_point(x: int, y: int, sleep_sec: Optional[float] = None) -> None:
    pyautogui.click(x, y)
    time.sleep(CFG.after_click_sleep_sec if sleep_sec is None else sleep_sec)


def click_template(template_name: str, timeout_sec: Optional[float] = None) -> Any:
    x, y, box = locate_center(template_path(template_name), timeout_sec=timeout_sec)
    click_point(x, y)
    return box


def click_template_optional(template_name: str, timeout_sec: float = 2.5) -> bool:
    try:
        click_template(template_name, timeout_sec=timeout_sec)
        return True
    except TimeoutError:
        return False


def wait_for_template(template_name: str, timeout_sec: float) -> Any:
    _, _, box = locate_center(template_path(template_name), timeout_sec=timeout_sec)
    return box


def take_screenshot(out_path: str) -> None:
    img = pyautogui.screenshot()
    img.save(out_path)


def ensure_board_screen_best_effort() -> None:
    pyautogui.moveTo(10, 10)
    time.sleep(0.1)
    click_template_optional("top_solver.png", timeout_sec=2.5)
    time.sleep(CFG.after_navigation_sleep_sec)

    pyautogui.moveTo(10, 10)
    time.sleep(0.1)
    click_template_optional("menu_board.png", timeout_sec=2.5)
    time.sleep(CFG.after_navigation_sleep_sec)


def run_solver_cycle_for_current_board() -> None:
    if not click_template_optional("menu_run_solver.png", timeout_sec=CFG.locate_timeout_sec):
        raise TimeoutError("Could not click left menu 'Run Solver'.")
    time.sleep(CFG.after_navigation_sleep_sec)

    if not click_template_optional("btn_build_new_tree.png", timeout_sec=CFG.locate_timeout_sec):
        raise TimeoutError("Could not click 'Build New Tree'.")
    time.sleep(CFG.after_navigation_sleep_sec)

    if not click_template_optional("btn_run_solver.png", timeout_sec=CFG.locate_timeout_sec):
        raise TimeoutError("Could not click panel 'Run Solver'.")
    time.sleep(CFG.after_solver_start_sleep_sec)

    wait_for_template("solver_finished.png", timeout_sec=6 * 60 * 60)


def go_to_results() -> None:
    if not click_template_optional("top_results.png", timeout_sec=CFG.locate_timeout_sec):
        raise TimeoutError("Could not click top menu 'Results'.")
    time.sleep(CFG.after_navigation_sleep_sec)


def _grab_screen_bgr() -> np.ndarray:
    img = np.array(ImageGrab.grab())
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def _detect_card_rects_in_grid(grid_bgr: np.ndarray) -> List[Tuple[int, int, int, int]]:
    gray = cv2.cvtColor(grid_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 40, 120)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rects = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if (CFG.min_card_w <= w <= CFG.max_card_w) and (CFG.min_card_h <= h <= CFG.max_card_h):
            if h > w:
                rects.append((x, y, w, h))

    rects = sorted(rects, key=lambda r: (r[1], r[0]))
    filtered = []
    for r in rects:
        x, y, w, h = r
        keep = True
        for fx, fy, fw, fh in filtered:
            if abs(x - fx) < 6 and abs(y - fy) < 6 and abs(w - fw) < 10 and abs(h - fh) < 10:
                keep = False
                break
        if keep:
            filtered.append(r)

    return filtered


def _cluster_rows(rects: List[Tuple[int, int, int, int]], n_rows: int = 4) -> List[List[Tuple[int, int, int, int]]]:
    if not rects:
        return []

    items = [(r, r[1] + r[3] / 2.0) for r in rects]
    items.sort(key=lambda t: t[1])

    rows: List[List[Tuple[int, int, int, int]]] = []
    for r, yc in items:
        placed = False
        for row in rows:
            row_yc = float(np.mean([rr[1] + rr[3] / 2.0 for rr in row]))
            if abs(yc - row_yc) < 25:
                row.append(r)
                placed = True
                break
        if not placed:
            rows.append([r])

    rows.sort(key=lambda row: float(np.mean([rr[1] + rr[3] / 2.0 for rr in row])))
    rows = sorted(rows, key=lambda row: abs(len(row) - 13))[:n_rows]
    rows.sort(key=lambda row: float(np.mean([rr[1] + rr[3] / 2.0 for rr in row])))

    for i in range(len(rows)):
        rows[i] = sorted(rows[i], key=lambda rr: rr[0])

    return rows


def get_grid_centers() -> List[List[Tuple[int, int]]]:
    _, _, board_title_box = locate_center(template_path("panel_board_title.png"), timeout_sec=CFG.locate_timeout_sec)

    grid_left = int(board_title_box.left + CFG.grid_offset_x)
    grid_top = int(board_title_box.top + CFG.grid_offset_y)
    grid_right = grid_left + CFG.grid_width
    grid_bottom = grid_top + CFG.grid_height

    screen_bgr = _grab_screen_bgr()
    grid_bgr = screen_bgr[grid_top:grid_bottom, grid_left:grid_right].copy()

    rects = _detect_card_rects_in_grid(grid_bgr)
    rows = _cluster_rows(rects, n_rows=4)

    if len(rows) != 4:
        raise RuntimeError(f"Grid detection failed: found {len(rows)} rows (expected 4).")

    centers: List[List[Tuple[int, int]]] = []
    for row in rows:
        if len(row) < 10:
            raise RuntimeError(f"Grid detection failed: a row has only {len(row)} rects.")
        row = row[:13]
        row_centers = []
        for x, y, w, h in row:
            cx = grid_left + int(x + w / 2)
            cy = grid_top + int(y + h / 2)
            row_centers.append((cx, cy))
        centers.append(row_centers)

    centers = [row[:13] for row in centers]
    return centers


def suit_row_index(letter: str) -> int:
    m = {"S": 0, "H": 1, "D": 2, "C": 3}
    if letter not in m:
        raise ValueError("suit_row_to_cycle must be one of: S, H, D, C")
    return m[letter]


def locate_oop_panel_box() -> Any:
    """
    OOP panel can appear in two sizes/states:
    - big: when nothing is selected yet
    - small: after selecting an option
    Try both quickly, then fall back to normal timeout.
    """
    for name in ("oop_panel_box_big.png", "oop_panel_box_small.png"):
        try:
            _, _, box = locate_center(template_path(name), timeout_sec=2.5)
            return box
        except TimeoutError:
            pass

    _, _, box = locate_center(template_path("oop_panel_box_small.png"), timeout_sec=CFG.locate_timeout_sec)
    return box


def click_oop_options_and_screenshot(card_id: str, out_dir: str) -> None:
    """
    Select OOP option 1, screenshot, option 2, screenshot, option 3, screenshot.

    Uses the OOP panel box position and proportional row geometry, so it works in both:
    - big panel (none selected)
    - small panel (after selection)
    """
    box = locate_oop_panel_box()

    left = box.left
    top = box.top
    w = box.width
    h = box.height

    click_x = int(left + max(12, w * CFG.oop_click_x_ratio))

    header_h = int(h * CFG.oop_header_ratio)
    rows_area_h = max(1, h - header_h)

    row_centers_y = []
    for i in range(CFG.oop_rows):
        ry = top + header_h + int((i + 0.5) * (rows_area_h / float(CFG.oop_rows)))
        row_centers_y.append(ry)

    for idx, ry in enumerate(row_centers_y, start=1):
        click_point(click_x, int(ry))
        time.sleep(0.35)
        out_path = os.path.join(out_dir, f"{card_id}_opt{idx}.png")
        take_screenshot(out_path)


def main() -> None:
    focus_app_window(CFG.app_window_title_contains)

    run_id = ts()
    out_dir = os.path.join(CFG.output_root, run_id)
    ensure_dir(out_dir)

    pyautogui.moveTo(10, 10)
    time.sleep(0.2)

    prev_cycle_center: Optional[Tuple[int, int]] = None
    row_idx = suit_row_index(CFG.suit_row_to_cycle)

    # Start on Board screen with your 2 fixed cards already selected.
    for rank_idx, rank in enumerate(CFG.ranks_in_order):
        card_id = f"{rank}{CFG.suit_row_to_cycle}"
        print(f"[{ts()}] Processing {card_id}")

        ensure_board_screen_best_effort()

        last_err = None
        centers = None
        for _ in range(CFG.grid_detect_retries):
            try:
                centers = get_grid_centers()
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(0.5)
        if centers is None:
            raise RuntimeError(f"Could not detect board grid. Last error: {last_err}")

        if CFG.deselect_previous_cycle_card and prev_cycle_center is not None:
            px, py = prev_cycle_center
            click_point(px, py)
            time.sleep(0.12)

        cx, cy = centers[row_idx][rank_idx]
        click_point(cx, cy)
        time.sleep(0.25)

        prev_cycle_center = (cx, cy)

        run_solver_cycle_for_current_board()

        go_to_results()
        click_oop_options_and_screenshot(card_id=card_id, out_dir=out_dir)

        ensure_board_screen_best_effort()

    print(f"[{ts()}] Done. Screenshots saved in: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    main()
