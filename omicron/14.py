"""
Square Image Multi-Colour Analyzer GUI
--------------------------------------

Features:
- Opens square images only
- Preserves multiple-colour image data
- Converts image internally to RGB for consistent output
- Displays the colour image and its file path
- Exports pixel sequence as:
    rgb.txt
    hex.txt

Dependencies:
    pip install pillow
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk


class SquareColourImageAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Square Multi-Colour Image Analyzer")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

        self.image_path = None
        self.tk_image = None

        self.build_ui()

    def build_ui(self):
        self.main_frame = tk.Frame(self.root, padx=12, pady=12)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.title_label = tk.Label(
            self.main_frame,
            text="Square Multi-Colour Image Analyzer",
            font=("Segoe UI", 18, "bold")
        )
        self.title_label.pack(anchor="w")

        self.button_frame = tk.Frame(self.main_frame)
        self.button_frame.pack(fill=tk.X, pady=(12, 8))

        self.open_button = tk.Button(
            self.button_frame,
            text="Open Square Image",
            command=self.open_image,
            height=2
        )
        self.open_button.pack(side=tk.LEFT)

        self.status_label = tk.Label(
            self.button_frame,
            text="Ready",
            anchor="w"
        )
        self.status_label.pack(side=tk.LEFT, padx=16)

        self.path_label = tk.Label(
            self.main_frame,
            text="Image file path: None",
            anchor="w",
            justify=tk.LEFT,
            wraplength=850
        )
        self.path_label.pack(fill=tk.X, pady=(4, 10))

        self.canvas_frame = tk.Frame(self.main_frame, bd=1, relief=tk.SUNKEN)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.canvas_frame, bg="#202020")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.output_label = tk.Label(
            self.main_frame,
            text="Output files: None",
            anchor="w",
            justify=tk.LEFT,
            wraplength=850
        )
        self.output_label.pack(fill=tk.X, pady=(10, 0))

    def open_image(self):
        path = filedialog.askopenfilename(
            title="Select a square image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        self.image_path = path
        self.set_busy(True)
        self.status_label.config(text="Processing image...")

        worker = threading.Thread(
            target=self.process_image_thread,
            args=(path,),
            daemon=True
        )
        worker.start()

    def process_image_thread(self, path):
        try:
            result = self.process_image(path)
            self.root.after(0, lambda: self.display_result(result))

        except Exception as error:
            self.root.after(0, lambda: self.handle_error(error))

    def process_image(self, path):
        image = Image.open(path)

        width, height = image.size

        if width != height:
            raise ValueError(
                f"The selected image is not square. "
                f"Detected dimensions: {width} x {height}"
            )

        # Convert to RGB so every pixel has exactly three values:
        # R, G, B.
        rgb_image = image.convert("RGB")

        directory = os.path.dirname(path)

        rgb_path = os.path.join(directory, "rgb.txt")
        hex_path = os.path.join(directory, "hex.txt")

        pixels = (
            list(rgb_image.get_flattened_data())
            if hasattr(rgb_image, "get_flattened_data")
            else list(rgb_image.getdata())
        )

        with open(rgb_path, "w", encoding="utf-8") as rgb_file, \
            open(hex_path, "w", encoding="utf-8") as hex_file:

            for index, (r, g, b) in enumerate(pixels):
                rgb_file.write(f"{index}: rgb({r}, {g}, {b})\n")
                hex_file.write(f"{index}: #{r:02X}{g:02X}{b:02X}\n")

        return {
            "image_path": path,
            "rgb_path": rgb_path,
            "hex_path": hex_path,
            "image": rgb_image,
            "size": rgb_image.size
        }

    def display_result(self, result):
        display_image = result["image"].copy()
        display_image.thumbnail((760, 480), Image.Resampling.LANCZOS)

        self.tk_image = ImageTk.PhotoImage(display_image)

        self.canvas.delete("all")

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width <= 1:
            canvas_width = 760

        if canvas_height <= 1:
            canvas_height = 480

        x = canvas_width // 2
        y = canvas_height // 2

        self.canvas.create_image(x, y, image=self.tk_image, anchor=tk.CENTER)

        self.path_label.config(
            text=f"Image file path: {result['image_path']}"
        )

        self.output_label.config(
            text=(
                f"Output files:\n"
                f"RGB sequence: {result['rgb_path']}\n"
                f"Hex sequence: {result['hex_path']}"
            )
        )

        width, height = result["size"]

        self.status_label.config(
            text=f"Complete. Image size: {width} x {height}"
        )

        self.set_busy(False)

    def handle_error(self, error):
        self.set_busy(False)
        self.status_label.config(text="Error")
        messagebox.showerror("Processing Error", str(error))

    def set_busy(self, busy):
        if busy:
            self.open_button.config(state=tk.DISABLED)
            self.root.config(cursor="watch")
        else:
            self.open_button.config(state=tk.NORMAL)
            self.root.config(cursor="")


def main():
    root = tk.Tk()
    app = SquareColourImageAnalyzerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
