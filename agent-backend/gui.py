#!/usr/bin/env python
"""
GUI Interface for Agentic Web Navigator - Easy Testing

Tkinter-based graphical interface for running web navigation tasks.
"""

import sys
import asyncio
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from threading import Thread
import json
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from main import WebNavigatorAgent
from config import Config
from utils import get_logger

logger = get_logger(__name__)


class WebNavigatorGUI:
    """Tkinter GUI for Agentic Web Navigator."""
    
    def __init__(self, root):
        """Initialize the GUI."""
        self.root = root
        self.root.title("Agentic Web Navigator - GUI Testing")
        
        # Set initial window size and center it
        window_width = 1000
        window_height = 800
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        self.root.resizable(True, True)
        
        # State
        self.agent = None
        self.is_running = False
        self.current_result = None
        
        # Setup styles
        self.setup_styles()
        
        # Create main layout
        self.create_widgets()
        
        # Configure grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
    
    def setup_styles(self):
        """Setup tkinter styles."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Button styles
        style.configure('Start.TButton', font=('Arial', 10, 'bold'))
        style.configure('Stop.TButton', font=('Arial', 10, 'bold'))
        style.configure('Save.TButton', font=('Arial', 9))
        style.configure('Clear.TButton', font=('Arial', 9))
    
    def create_widgets(self):
        """Create all GUI widgets."""
        # Title
        title_frame = ttk.Frame(self.root)
        title_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=10)
        
        title_label = ttk.Label(
            title_frame,
            text="🤖 Agentic Web Navigator - Testing Interface",
            font=('Arial', 16, 'bold')
        )
        title_label.pack(side='left')
        
        # Input section
        input_frame = ttk.LabelFrame(self.root, text="Task Configuration", padding=10)
        input_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=5)
        input_frame.columnconfigure(1, weight=1)
        
        # Goal input
        ttk.Label(input_frame, text="Task Goal:", font=('Arial', 10, 'bold')).grid(
            row=0, column=0, sticky='nw', padx=5, pady=5
        )
        
        self.goal_text = tk.Text(input_frame, height=3, width=60, font=('Arial', 10))
        self.goal_text.grid(row=0, column=1, sticky='ew', padx=5, pady=5)
        self.goal_text.insert('1.0', "Search for 'Python' on Google")
        
        # Options frame
        options_frame = ttk.Frame(input_frame)
        options_frame.grid(row=1, column=0, columnspan=2, sticky='ew', padx=5, pady=10)
        
        # Checkboxes
        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame,
            text="Headless (hidden browser)",
            variable=self.headless_var
        ).pack(side='left', padx=10)
        
        self.mock_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame,
            text="Mock Mode (no API)",
            variable=self.mock_var
        ).pack(side='left', padx=10)
        
        # Max steps
        ttk.Label(options_frame, text="Max Steps:").pack(side='left', padx=10)
        self.max_steps_var = tk.StringVar(value="20")
        steps_spinbox = ttk.Spinbox(
            options_frame,
            from_=1,
            to=100,
            textvariable=self.max_steps_var,
            width=5
        )
        steps_spinbox.pack(side='left', padx=5)
        
        # Control buttons
        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky='ew', padx=5, pady=10)
        
        self.start_button = ttk.Button(
            button_frame,
            text="▶ START TASK",
            command=self.start_task,
            style='Start.TButton'
        )
        self.start_button.pack(side='left', padx=5)
        
        self.stop_button = ttk.Button(
            button_frame,
            text="⏹ STOP",
            command=self.stop_task,
            style='Stop.TButton',
            state='disabled'
        )
        self.stop_button.pack(side='left', padx=5)
        
        ttk.Button(
            button_frame,
            text="💾 Save Result",
            command=self.save_result,
            style='Save.TButton'
        ).pack(side='left', padx=5)
        
        ttk.Button(
            button_frame,
            text="🗑 Clear Log",
            command=self.clear_log,
            style='Clear.TButton'
        ).pack(side='left', padx=5)
        
        # Status indicator
        self.status_label = ttk.Label(
            button_frame,
            text="Status: READY",
            font=('Arial', 10, 'bold'),
            foreground='green'
        )
        self.status_label.pack(side='right', padx=10)
        
        # Output section
        output_frame = ttk.LabelFrame(self.root, text="Execution Log", padding=10)
        output_frame.grid(row=2, column=0, sticky='nsew', padx=10, pady=5)
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        
        # Log text
        self.log_text = scrolledtext.ScrolledText(
            output_frame,
            height=25,
            width=80,
            font=('Courier', 9),
            bg='#f0f0f0',
            fg='#000000'
        )
        self.log_text.grid(row=0, column=0, sticky='nsew')
        
        # Configure tags for colored output
        self.log_text.tag_config('info', foreground='#0066cc')
        self.log_text.tag_config('success', foreground='#00aa00')
        self.log_text.tag_config('error', foreground='#cc0000')
        self.log_text.tag_config('warning', foreground='#ff6600')
        self.log_text.tag_config('step', foreground='#6600cc', font=('Courier', 9, 'bold'))
        self.log_text.tag_config('action', foreground='#0099cc')
        
        # Results section
        results_frame = ttk.LabelFrame(self.root, text="Task Summary", padding=10)
        results_frame.grid(row=3, column=0, sticky='ew', padx=10, pady=5)
        results_frame.columnconfigure(0, weight=1)
        
        self.results_text = scrolledtext.ScrolledText(
            results_frame,
            height=6,
            width=80,
            font=('Courier', 9),
            bg='#f9f9f9',
            fg='#000000'
        )
        self.results_text.grid(row=0, column=0, sticky='nsew')
        
        self.results_text.tag_config('header', font=('Courier', 10, 'bold'), foreground='#000000')
        self.results_text.tag_config('success_result', foreground='#00aa00')
        self.results_text.tag_config('fail_result', foreground='#cc0000')
    
    def log(self, message, tag='info'):
        """Log message to output."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        self.log_text.insert('end', log_line, tag)
        self.log_text.see('end')
        self.root.update()
    
    def start_task(self):
        """Start task execution in background thread."""
        goal = self.goal_text.get('1.0', 'end').strip()
        
        if not goal:
            messagebox.showwarning("Invalid Input", "Please enter a task goal")
            return
        
        if not self.mock_var.get() and not Config.GROQ_API_KEY:
            messagebox.showerror(
                "API Key Missing",
                "GROQ_API_KEY not configured.\n\n"
                "Either:\n"
                "1. Set API key in .env file, or\n"
                "2. Use Mock Mode (no API needed)"
            )
            return
        
        # Disable controls
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.goal_text.config(state='disabled')
        self.is_running = True
        
        # Update status
        self.update_status("RUNNING", "orange")
        self.log("=" * 60, 'info')
        self.log("TASK STARTED", 'info')
        self.log("=" * 60, 'info')
        
        # Run in background thread
        thread = Thread(target=self._run_task, args=(goal,), daemon=True)
        thread.start()
    
    def _run_task(self, goal):
        """Run task in background (internal)."""
        try:
            # Parse options
            max_steps = int(self.max_steps_var.get())
            headless = self.headless_var.get()
            use_mock = self.mock_var.get()
            
            self.log(f"Goal: {goal}", 'step')
            self.log(f"Mode: {'MOCK' if use_mock else 'LIVE'}", 'action')
            self.log(f"Browser: {'Headless' if headless else 'Visible'}", 'action')
            self.log(f"Max Steps: {max_steps}", 'action')
            self.log("", 'info')
            
            # Create agent
            agent = WebNavigatorAgent(
                goal=goal,
                max_steps=max_steps,
                headless=headless,
                use_mock=use_mock
            )
            
            # Run asyncio loop
            result = asyncio.run(agent.run())
            
            # Store result
            self.current_result = result
            
            # Display results
            self._display_results(result)
            
            # Update status
            status = result.get('status', 'unknown').upper()
            if status == 'COMPLETED':
                self.update_status(f"✓ {status}", "green")
                self.log("✓ TASK COMPLETED SUCCESSFULLY", 'success')
            else:
                self.update_status(f"✗ {status}", "red")
                self.log(f"✗ TASK {status}", 'error')
            
        except Exception as e:
            self.log(f"✗ ERROR: {str(e)}", 'error')
            self.update_status("ERROR", "red")
            messagebox.showerror("Task Error", f"Error: {str(e)}")
        
        finally:
            self.is_running = False
            self.start_button.config(state='normal')
            self.stop_button.config(state='disabled')
            self.goal_text.config(state='normal')
            self.log("=" * 60, 'info')
    
    def _display_results(self, result):
        """Display task results in summary section."""
        self.results_text.config(state='normal')
        self.results_text.delete('1.0', 'end')
        
        # Header
        self.results_text.insert('end', "TASK SUMMARY\n", 'header')
        self.results_text.insert('end', "=" * 70 + "\n", 'info')
        
        # Status
        status = result.get('status', 'unknown')
        status_tag = 'success_result' if status == 'completed' else 'fail_result'
        self.results_text.insert('end', f"Status: {status.upper()}\n", status_tag)
        
        # Metrics
        self.results_text.insert(
            'end',
            f"Steps: {result.get('total_steps', 0)}/{result.get('max_steps', 0)}\n",
            'info'
        )
        self.results_text.insert(
            'end',
            f"Successful: {result.get('successful_actions', 0)}\n",
            'success_result'
        )
        self.results_text.insert(
            'end',
            f"Failed: {result.get('failed_actions', 0)}\n",
            'fail_result'
        )
        
        # Action sequence
        self.results_text.insert('end', "\nAction Sequence:\n", 'header')
        for step in result.get('action_sequence', [])[:10]:  # Show first 10
            status_char = "✓" if step['success'] else "✗"
            tag = 'success_result' if step['success'] else 'fail_result'
            self.results_text.insert(
                'end',
                f"  {status_char} Step {step['step']}: {step['action']}\n",
                tag
            )
        
        if len(result.get('action_sequence', [])) > 10:
            self.results_text.insert('end', f"  ... and {len(result['action_sequence']) - 10} more steps\n", 'info')
        
        self.results_text.config(state='disabled')
    
    def stop_task(self):
        """Stop task execution."""
        self.is_running = False
        self.log("⏹ Task stopped by user", 'warning')
        
        # Reset controls
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.goal_text.config(state='normal')
        self.update_status("STOPPED", "orange")
    
    def clear_log(self):
        """Clear log output."""
        if messagebox.askyesno("Clear Log", "Clear all log messages?"):
            self.log_text.delete('1.0', 'end')
            self.log("Log cleared", 'info')
    
    def save_result(self):
        """Save result to JSON file."""
        if not self.current_result:
            messagebox.showwarning("No Result", "No task result to save. Run a task first.")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"navigator_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    json.dump(self.current_result, f, indent=2)
                messagebox.showinfo("Success", f"Result saved to:\n{filename}")
                self.log(f"✓ Result saved to {filename}", 'success')
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")
                self.log(f"✗ Failed to save result: {e}", 'error')
    
    def update_status(self, text, color):
        """Update status indicator."""
        color_map = {
            'green': '#00aa00',
            'red': '#cc0000',
            'orange': '#ff6600',
        }
        self.status_label.config(
            text=f"Status: {text}",
            foreground=color_map.get(color, '#000000')
        )


def main():
    """Run the GUI application."""
    root = tk.Tk()
    
    # Create GUI
    gui = WebNavigatorGUI(root)
    
    # Initial log
    gui.log("Welcome to Agentic Web Navigator", 'info')
    gui.log("", 'info')
    gui.log("Instructions:", 'info')
    gui.log("1. Enter your task goal (e.g., 'Search for Python on Google')", 'info')
    gui.log("2. Configure options (headless mode, mock mode, max steps)", 'info')
    gui.log("3. Click START TASK to begin", 'info')
    gui.log("", 'info')
    
    if not Config.GROQ_API_KEY:
        gui.log("⚠️  GROQ_API_KEY not configured", 'warning')
        gui.log("Use Mock Mode (no API) for testing, or set your API key in .env", 'warning')
        gui.log("", 'info')
    
    gui.log("Ready to navigate! 🚀", 'success')
    
    # Run
    root.mainloop()


if __name__ == "__main__":
    main()
