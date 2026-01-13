"""
Desktop Postflop automator (Board grid detection, supports fixed selected cards)

Use case:
- You manually keep 2 fixed cards selected (any suit rows).
- Script cycles a third card across one suit row (A..2), keeping the fixed cards selected.
- No reliance on card templates (selected state can change appearance).

How it works:
- Anchors on the "Board" title in the main panel via template (stable UI text).
- Crops a region below it where the 4 suit rows exist.
- Uses OpenCV to detect card rectangles (borders), independent of fill color (yellow selection).
- Sorts rectangles into 4 rows x 13 columns and clicks the target cell center.

Dependencies:
pip install pyautogui opencv-python pillow numpy pygetwindow

Templates needed in ./templates:
- panel_board_title.png   (crop of the "Board" title in the MAIN panel, not side menu, neutral state)
- menu_run_solver.png
- btn_build_new_tree.png
- btn_run_solver.png
- solver_finished.png
- top_results.png
- oop_label.png
- top_solver.png
- menu_board.png          (optional best-effort)
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

    # Results -> OOP options positions relative to "OOP" label
    oop_first_row_offset_y: int = 55
    oop_row_step_y: int = 24

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
    suit_row_to_cycle: str = "S"  # "S", "H", "D", "C" (row order in UI is assumed S,H,D,C top->bottom)
    deselect_previous_cycle_card: bool = True

    # If detection fails, retry how many times
    grid_detect_retries: int = 3


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


def click_oop_options_and_screenshot(card_id: str, out_dir: str) -> None:
    x, y, _ = locate_center(template_path("oop_label.png"), timeout_sec=CFG.locate_timeout_sec)
    base_x = x + 60

    for idx in range(3):
        row_y = y + CFG.oop_first_row_offset_y + idx * CFG.oop_row_step_y
        click_point(base_x, row_y)
        time.sleep(0.35)
        out_path = os.path.join(out_dir, f"{card_id}_opt{idx+1}.png")
        take_screenshot(out_path)


def _grab_screen_bgr() -> np.ndarray:
    img = np.array(ImageGrab.grab())
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def _detect_card_rects_in_grid(grid_bgr: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """
    Detect card rectangles using edges/contours. Works even if cards are yellow/selected.
    Returns list of (x,y,w,h) in grid coordinates.
    """
    gray = cv2.cvtColor(grid_bgr, cv2.COLOR_BGR2GRAY)
    # Emphasize borders
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 40, 120)

    # Close gaps in borders
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rects = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if (CFG.min_card_w <= w <= CFG.max_card_w) and (CFG.min_card_h <= h <= CFG.max_card_h):
            # Basic shape sanity: cards should be taller than wide
            if h > w:
                rects.append((x, y, w, h))

    # Remove near-duplicates by IOU-like grouping (simple)
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
    """
    Cluster rectangles into rows by their y-centers.
    """
    if not rects:
        return []

    # Compute y centers
    items = [(r, r[1] + r[3] / 2.0) for r in rects]
    items.sort(key=lambda t: t[1])

    # Greedy clustering by proximity
    rows: List[List[Tuple[int, int, int, int]]] = []
    for r, yc in items:
        placed = False
        for row in rows:
            row_yc = np.mean([rr[1] + rr[3] / 2.0 for rr in row])
            if abs(yc - row_yc) < 25:  # row separation threshold
                row.append(r)
                placed = True
                break
        if not placed:
            rows.append([r])

    # Sort rows by y and keep the best 4 (closest to 13 items)
    rows.sort(key=lambda row: np.mean([rr[1] + rr[3] / 2.0 for rr in row]))
    rows = sorted(rows, key=lambda row: abs(len(row) - 13))[:n_rows]
    rows.sort(key=lambda row: np.mean([rr[1] + rr[3] / 2.0 for rr in row]))

    # Sort each row by x
    for i in range(len(rows)):
        rows[i] = sorted(rows[i], key=lambda rr: rr[0])

    return rows


def get_grid_centers() -> List[List[Tuple[int, int]]]:
    """
    Returns centers for 4 rows x 13 cols in ABSOLUTE screen coordinates.
    Row order assumption: [Spades, Hearts, Diamonds, Clubs] top->bottom
    """
    # Anchor on the main panel title "Board"
    _, _, board_title_box = locate_center(template_path("panel_board_title.png"), timeout_sec=CFG.locate_timeout_sec)

    grid_left = int(board_title_box.left + CFG.grid_offset_x)
    grid_top = int(board_title_box.top + CFG.grid_offset_y)
    grid_right = grid_left + CFG.grid_width
    grid_bottom = grid_top + CFG.grid_height

    screen_bgr = _grab_screen_bgr()
    grid_bgr = screen_bgr[grid_top:grid_bottom, grid_left:grid_right].copy()

    rects = _detect_card_rects_in_grid(grid_bgr)
    rows = _cluster_rows(rects, n_rows=4)

    # Validate: need 4 rows and each close to 13
    if len(rows) != 4:
        raise RuntimeError(f"Grid detection failed: found {len(rows)} rows (expected 4).")

    centers: List[List[Tuple[int, int]]] = []
    for row in rows:
        if len(row) < 10:
            raise RuntimeError(f"Grid detection failed: a row has only {len(row)} rects.")
        # keep leftmost 13 if extras
        row = row[:13]
        row_centers = []
        for x, y, w, h in row:
            cx = grid_left + int(x + w / 2)
            cy = grid_top + int(y + h / 2)
            row_centers.append((cx, cy))
        centers.append(row_centers)

    # If a row has not exactly 13, normalize by trimming to 13
    centers = [row[:13] for row in centers]
    return centers


def suit_row_index(letter: str) -> int:
    # Assumed UI order (your screenshot): Spades, Hearts, Diamonds, Clubs
    m = {"S": 0, "H": 1, "D": 2, "C": 3}
    if letter not in m:
        raise ValueError("suit_row_to_cycle must be one of: S, H, D, C")
    return m[letter]


def main() -> None:
    focus_app_window(CFG.app_window_title_contains)

    run_id = ts()
    out_dir = os.path.join(CFG.output_root, run_id)
    ensure_dir(out_dir)

    # Avoid hover-state mismatches
    pyautogui.moveTo(10, 10)
    time.sleep(0.2)

    prev_cycle_center: Optional[Tuple[int, int]] = None
    row_idx = suit_row_index(CFG.suit_row_to_cycle)

    # Start on Board screen with your 2 fixed cards already selected.
    for rank_idx, rank in enumerate(CFG.ranks_in_order):
        card_id = f"{rank}{CFG.suit_row_to_cycle}"
        print(f"[{ts()}] Processing {card_id}")

        # Make sure we are on Board (best effort)
        ensure_board_screen_best_effort()

        # Detect grid centers (retry a few times if needed)
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

        # Deselect previous cycle card only (do NOT clear fixed cards)
        if CFG.deselect_previous_cycle_card and prev_cycle_center is not None:
            px, py = prev_cycle_center
            click_point(px, py)
            time.sleep(0.12)

        # Select current cycle card in the chosen suit row and rank column
        cx, cy = centers[row_idx][rank_idx]
        click_point(cx, cy)
        time.sleep(0.25)

        prev_cycle_center = (cx, cy)

        # Solve
        run_solver_cycle_for_current_board()

        # Results + screenshots
        go_to_results()
        click_oop_options_and_screenshot(card_id=card_id, out_dir=out_dir)

        # Back to Board for next iteration
        ensure_board_screen_best_effort()

    print(f"[{ts()}] Done. Screenshots saved in: {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    main()
