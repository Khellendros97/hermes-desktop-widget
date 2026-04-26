# Panel Animation Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Dynamic Island expand/collapse feel smoother with subtle elasticity and fewer geometry/layout stalls.

**Architecture:** Keep the existing geometry animation approach, but make animation lifetime explicit with `self._anim`, choose easing by transition direction, and defer fixed-size locking until animation completion. No new animation framework or visual redesign.

**Tech Stack:** PyQt6 `QPropertyAnimation`, `QEasingCurve`, existing `DynamicIsland` widget.

---

### Task 1: Smooth Geometry Animation

**Files:**
- Modify: `hermes_panel/panel.py:362`

**Step 1: Implement minimal animation helper**
- Add `self._anim = None` in `DynamicIsland.__init__`.
- Add `_animation_profile(target_state)` returning duration/easing:
  - `HIDDEN`: `240ms`, `InOutCubic`
  - `NOTIFY`: `320ms`, `OutBack`
  - `CHAT`: `360ms`, `OutBack`
- Store `QPropertyAnimation` on `self._anim`.
- Before animation, call `setMinimumSize(0, 0)` and `setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)`.
- On finish, lock `setFixedSize(target.size())`.

**Step 2: Verify**
Run: `python -c "from hermes_panel.panel import DynamicIsland; print('ok')"`
Expected: `ok`

### Task 2: Validate Existing Behavior

**Files:**
- Test: `tests/`

**Step 1: Run tests**
Run: `python -m pytest tests/ -q`
Expected: all tests pass.

**Step 2: Restart app**
Run: `taskkill /f /im python.exe 2>$null; Start-Process -FilePath python -ArgumentList "main.py" -WorkingDirectory "D:\projects\hermes-panel" -NoNewWindow`
Expected: panel starts and connects.
