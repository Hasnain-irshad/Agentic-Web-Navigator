#!/usr/bin/env python
"""
Interactive Session GUI for Agentic Web Navigator

Tkinter-based interface with persistent browser session.
Browser stays open between commands for continuous interaction.
"""

import sys
import asyncio
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from threading import Thread
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.session_agent import SessionAgent
from config import Config
from utils import get_logger

logger = get_logger(__name__)


class SessionGUI:
    """Interactive Session GUI for continuous browser control."""
    
    def __init__(self, root):
        """Initialize the GUI."""
        self.root = root
        self.root.title("🤖 Agentic Web Navigator - Interactive Session")
        
        # Window setup
        window_width = 1100
        window_height = 850
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.resizable(True, True)
        
        # State
        self.session_agent: SessionAgent = None
        self.session_active = False
        self.command_running = False
        self.async_loop = None
        
        # Setup
        self.setup_styles()
        self.create_widgets()
        
        # Grid config
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)
    
    def setup_styles(self):
        """Setup tkinter styles."""
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('Session.TButton', font=('Arial', 11, 'bold'))
        style.configure('Command.TButton', font=('Arial', 10, 'bold'))
        style.configure('End.TButton', font=('Arial', 10))
    
    def create_widgets(self):
        """Create all GUI widgets."""
        # Title
        title_frame = ttk.Frame(self.root)
        title_frame.grid(row=0, column=0, sticky='ew', padx=10, pady=10)
        
        ttk.Label(
            title_frame,
            text="🤖 Agentic Web Navigator - Interactive Session",
            font=('Arial', 16, 'bold')
        ).pack(side='left')
        
        # Session Controls
        session_frame = ttk.LabelFrame(self.root, text="Session Control", padding=10)
        session_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=5)
        session_frame.columnconfigure(1, weight=1)
        
        # Session buttons
        btn_frame = ttk.Frame(session_frame)
        btn_frame.grid(row=0, column=0, sticky='w')
        
        self.start_session_btn = ttk.Button(
            btn_frame,
            text="🚀 Start Session",
            command=self.start_session,
            style='Session.TButton'
        )
        self.start_session_btn.pack(side='left', padx=5)
        
        self.end_session_btn = ttk.Button(
            btn_frame,
            text="🛑 End Session",
            command=self.end_session,
            style='End.TButton',
            state='disabled'
        )
        self.end_session_btn.pack(side='left', padx=5)
        
        # Options
        options_frame = ttk.Frame(session_frame)
        options_frame.grid(row=0, column=1, sticky='e')
        
        self.mock_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options_frame,
            text="Mock Mode (no API)",
            variable=self.mock_var
        ).pack(side='left', padx=5)
        
        ttk.Label(options_frame, text="Max Steps:").pack(side='left', padx=5)
        self.max_steps_var = tk.StringVar(value="15")
        ttk.Spinbox(
            options_frame,
            from_=5, to=50,
            textvariable=self.max_steps_var,
            width=4
        ).pack(side='left', padx=2)
        
        # Status
        self.session_status = ttk.Label(
            session_frame,
            text="Session: INACTIVE",
            font=('Arial', 10, 'bold'),
            foreground='gray'
        )
        self.session_status.grid(row=1, column=0, columnspan=2, sticky='w', pady=5)
        
        # Current page info
        self.page_info = ttk.Label(
            session_frame,
            text="Page: (no active session)",
            font=('Arial', 9),
            foreground='#666'
        )
        self.page_info.grid(row=2, column=0, columnspan=2, sticky='w')
        
        # Command Input
        command_frame = ttk.LabelFrame(self.root, text="Command Input", padding=10)
        command_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=5)
        command_frame.columnconfigure(0, weight=1)
        
        # Command text
        self.command_text = tk.Text(command_frame, height=2, font=('Arial', 11))
        self.command_text.grid(row=0, column=0, sticky='ew', padx=5, pady=5)
        self.command_text.insert('1.0', "Search for 'Python tutorials' on Google")
        self.command_text.config(state='disabled')
        
        # Send button
        self.send_btn = ttk.Button(
            command_frame,
            text="▶ Send Command",
            command=self.send_command,
            style='Command.TButton',
            state='disabled'
        )
        self.send_btn.grid(row=0, column=1, padx=5, pady=5)
        
        # Quick commands
        quick_frame = ttk.Frame(command_frame)
        quick_frame.grid(row=1, column=0, columnspan=2, sticky='w', pady=5)
        
        ttk.Label(quick_frame, text="Quick:", font=('Arial', 9)).pack(side='left', padx=5)
        
        quick_commands = [
            ("Scroll Down", "Scroll down the page"),
            ("Scroll Up", "Scroll up the page"),
            ("Go Back", "Go back to previous page"),
            ("Click First Link", "Click on the first link on this page"),
        ]
        
        for label, cmd in quick_commands:
            ttk.Button(
                quick_frame,
                text=label,
                command=lambda c=cmd: self.quick_command(c),
                state='disabled'
            ).pack(side='left', padx=2)
        
        self.quick_buttons = quick_frame.winfo_children()[1:]  # Skip label
        
        # Log Output
        log_frame = ttk.LabelFrame(self.root, text="Activity Log", padding=10)
        log_frame.grid(row=3, column=0, sticky='nsew', padx=10, pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=20,
            font=('Consolas', 9),
            bg='#1e1e1e',
            fg='#d4d4d4'
        )
        self.log_text.grid(row=0, column=0, sticky='nsew')
        
        # Log tags
        self.log_text.tag_config('info', foreground='#569cd6')
        self.log_text.tag_config('success', foreground='#4ec9b0')
        self.log_text.tag_config('error', foreground='#f14c4c')
        self.log_text.tag_config('command', foreground='#dcdcaa', font=('Consolas', 9, 'bold'))
        self.log_text.tag_config('action', foreground='#ce9178')
        self.log_text.tag_config('system', foreground='#808080')
        
        # Command History
        history_frame = ttk.LabelFrame(self.root, text="Command History", padding=10)
        history_frame.grid(row=4, column=0, sticky='ew', padx=10, pady=5)
        history_frame.columnconfigure(0, weight=1)
        
        self.history_text = scrolledtext.ScrolledText(
            history_frame,
            height=4,
            font=('Consolas', 9),
            bg='#252526',
            fg='#cccccc'
        )
        self.history_text.grid(row=0, column=0, sticky='ew')
        self.history_text.config(state='disabled')
    
    def log(self, message: str, tag: str = 'info'):
        """Add message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert('end', f"[{timestamp}] {message}\n", tag)
        self.log_text.see('end')
        self.root.update()
    
    def update_session_status(self, status: str, color: str):
        """Update session status display."""
        self.session_status.config(text=f"Session: {status}", foreground=color)
    
    def update_page_info(self, url: str, title: str):
        """Update current page info."""
        display_url = url[:80] + "..." if len(url) > 80 else url
        self.page_info.config(text=f"Page: {title} | {display_url}")
    
    def set_controls_state(self, session_active: bool, command_running: bool = False):
        """Enable/disable controls based on state."""
        if session_active:
            self.start_session_btn.config(state='disabled')
            self.end_session_btn.config(state='normal' if not command_running else 'disabled')
            self.command_text.config(state='normal' if not command_running else 'disabled')
            self.send_btn.config(state='normal' if not command_running else 'disabled')
            for btn in self.quick_buttons:
                btn.config(state='normal' if not command_running else 'disabled')
        else:
            self.start_session_btn.config(state='normal')
            self.end_session_btn.config(state='disabled')
            self.command_text.config(state='disabled')
            self.send_btn.config(state='disabled')
            for btn in self.quick_buttons:
                btn.config(state='disabled')
    
    def start_session(self):
        """Start browser session."""
        if not self.mock_var.get() and not Config.GROQ_API_KEY:
            messagebox.showerror(
                "API Key Missing",
                "GROQ_API_KEY not set. Use Mock Mode or add API key to .env"
            )
            return
        
        self.log("Starting browser session...", 'system')
        self.update_session_status("STARTING...", "orange")
        
        # Create session agent
        self.session_agent = SessionAgent(
            max_steps_per_command=int(self.max_steps_var.get()),
            headless=False,  # Always visible for interactive mode
            use_mock=self.mock_var.get()
        )
        
        # Start in background
        thread = Thread(target=self._start_session_async, daemon=True)
        thread.start()
    
    def _start_session_async(self):
        """Background thread for starting session."""
        try:
            self.async_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.async_loop)
            
            result = self.async_loop.run_until_complete(
                self.session_agent.start_session()
            )
            
            if result['status'] == 'started':
                self.session_active = True
                self.root.after(0, lambda: self.update_session_status("ACTIVE ✓", "green"))
                self.root.after(0, lambda: self.set_controls_state(True))
                self.root.after(0, lambda: self.log("✓ Session started! Enter commands below.", 'success'))
                self.root.after(0, lambda: self.log("Browser is ready. Type a command and click 'Send Command'.", 'info'))
            else:
                self.root.after(0, lambda: self.update_session_status("FAILED", "red"))
                self.root.after(0, lambda: self.log(f"✗ Failed: {result.get('message', 'Unknown error')}", 'error'))
                
        except Exception as e:
            self.root.after(0, lambda: self.update_session_status("ERROR", "red"))
            self.root.after(0, lambda e=e: self.log(f"✗ Error: {str(e)}", 'error'))
    
    def send_command(self):
        """Send command to browser."""
        if not self.session_active:
            return
        
        command = self.command_text.get('1.0', 'end').strip()
        if not command:
            messagebox.showwarning("Empty Command", "Please enter a command")
            return
        
        self.command_running = True
        self.set_controls_state(True, command_running=True)
        
        self.log("=" * 50, 'system')
        self.log(f"COMMAND: {command}", 'command')
        self.log("=" * 50, 'system')
        
        thread = Thread(target=self._execute_command_async, args=(command,), daemon=True)
        thread.start()
    
    def _execute_command_async(self, command: str):
        """Background thread for command execution."""
        try:
            def callback(stage, message):
                self.root.after(0, lambda: self.log(f"  [{stage}] {message}", 'action'))
            
            result = self.async_loop.run_until_complete(
                self.session_agent.execute_command(command, callback)
            )
            
            # Update history
            self.root.after(0, lambda: self._add_to_history(command, result))
            
            # Update page info
            page_info = self.async_loop.run_until_complete(
                self.session_agent.get_current_page_info()
            )
            self.root.after(0, lambda: self.update_page_info(
                page_info.get('url', ''),
                page_info.get('title', '')
            ))
            
            # Log result
            status = result.get('status', 'unknown')
            if status in ['completed', 'partial']:
                self.root.after(0, lambda: self.log(
                    f"✓ Command completed ({result.get('successful', 0)}/{result.get('steps', 0)} successful)",
                    'success'
                ))
            else:
                self.root.after(0, lambda: self.log(
                    f"✗ Command failed: {result.get('message', 'Unknown')}",
                    'error'
                ))
            
            self.root.after(0, lambda: self.log("Ready for next command.", 'info'))
            
        except Exception as e:
            self.root.after(0, lambda e=e: self.log(f"✗ Error: {str(e)}", 'error'))
        
        finally:
            self.command_running = False
            self.root.after(0, lambda: self.set_controls_state(True))
    
    def _add_to_history(self, command: str, result: dict):
        """Add command to history display."""
        self.history_text.config(state='normal')
        status = "✓" if result.get('status') in ['completed', 'partial'] else "✗"
        self.history_text.insert('end', f"{status} {command[:60]}...\n" if len(command) > 60 else f"{status} {command}\n")
        self.history_text.see('end')
        self.history_text.config(state='disabled')
    
    def quick_command(self, command: str):
        """Execute a quick command."""
        self.command_text.config(state='normal')
        self.command_text.delete('1.0', 'end')
        self.command_text.insert('1.0', command)
        self.send_command()
    
    def end_session(self):
        """End browser session."""
        if not self.session_active:
            return
        
        self.log("Ending session...", 'system')
        
        thread = Thread(target=self._end_session_async, daemon=True)
        thread.start()
    
    def _end_session_async(self):
        """Background thread for ending session."""
        try:
            result = self.async_loop.run_until_complete(
                self.session_agent.end_session()
            )
            
            self.session_active = False
            self.root.after(0, lambda: self.update_session_status("ENDED", "gray"))
            self.root.after(0, lambda: self.set_controls_state(False))
            self.root.after(0, lambda: self.update_page_info("", "(session ended)"))
            self.root.after(0, lambda: self.log(
                f"Session ended. Total commands: {result.get('total_commands', 0)}",
                'system'
            ))
            
            if self.async_loop:
                self.async_loop.close()
                self.async_loop = None
            
        except Exception as e:
            self.root.after(0, lambda e=e: self.log(f"Error ending session: {e}", 'error'))


def main():
    """Run the interactive session GUI."""
    root = tk.Tk()
    gui = SessionGUI(root)
    
    # Initial log
    gui.log("Welcome to Agentic Web Navigator - Interactive Session Mode", 'info')
    gui.log("", 'info')
    gui.log("How to use:", 'info')
    gui.log("1. Click 'Start Session' to launch browser", 'info')
    gui.log("2. Enter commands like 'Search for Python on Google'", 'info')
    gui.log("3. Browser stays open - enter more commands!", 'info')
    gui.log("4. Click 'End Session' when done", 'info')
    gui.log("", 'info')
    
    if not Config.GROQ_API_KEY:
        gui.log("⚠️ GROQ_API_KEY not set - use Mock Mode for testing", 'error')
    
    root.mainloop()


if __name__ == "__main__":
    main()
