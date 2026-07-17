"""
Square Image Greyscale Analyzer GUI
-----------------------------------

Features:
- Opens square images only
- Accepts RGB, RGBA, greyscale, and other Pillow-supported formats
- Converts non-greyscale images to greyscale automatically
- Displays the greyscale image in the GUI
- Displays the greyscale image file path
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


class SquareImageAnalyzerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Square Image Greyscale Analyzer")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

        self.original_path = None
        self.greyscale_path = None
        self.tk_image = None

        self.build_ui()

    def build_ui(self):
        self.main_frame = tk.Frame(self.root, padx=12, pady=12)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.title_label = tk.Label(
            self.main_frame,
            text="Square Image Greyscale Analyzer",
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
            text="Greyscale file path: None",
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

        self.original_path = path
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

        # Convert to greyscale if required.
        # Pillow mode "L" means 8-bit greyscale.
        if image.mode != "L":
            greyscale_image = image.convert("L")
        else:
            greyscale_image = image.copy()

        directory = os.path.dirname(path)
        filename_without_ext = os.path.splitext(os.path.basename(path))[0]

        greyscale_path = os.path.join(
            directory,
            f"{filename_without_ext}_greyscale.png"
        )

        rgb_path = os.path.join(directory, "rgb.txt")
        hex_path = os.path.join(directory, "hex.txt")

        greyscale_image.save(greyscale_path)

        pixels = list(greyscale_image.getdata())

        with open(rgb_path, "w", encoding="utf-8") as rgb_file, \
             open(hex_path, "w", encoding="utf-8") as hex_file:

            for index, grey_value in enumerate(pixels):
                r = grey_value
                g = grey_value
                b = grey_value

                rgb_file.write(f"{index}: rgb({r}, {g}, {b})\n")
                hex_file.write(f"{index}: #{r:02X}{g:02X}{b:02X}\n")

        return {
            "greyscale_path": greyscale_path,
            "rgb_path": rgb_path,
            "hex_path": hex_path,
            "image": greyscale_image,
            "size": greyscale_image.size
        }

    def display_result(self, result):
        self.greyscale_path = result["greyscale_path"]

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
            text=f"Greyscale file path: {result['greyscale_path']}"
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
    app = SquareImageAnalyzerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
