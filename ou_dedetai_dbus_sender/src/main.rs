use std::time::Duration;

use dbus::{
    Message,
    blocking::{BlockingSender, Connection},
};

const TIMEOUT: Duration = Duration::from_secs(30);

fn main() {
    let c = Connection::new_session();
    if let Err(error) = &c {
        eprintln!("Failed to connect to system bus: {}", error);
    }
    let c = c.unwrap();

    // Prepare arguments for forwarding
    let mut arguments = Vec::new();
    arguments.extend(std::env::args());
    // Remove the first argument (binary path)
    arguments.remove(0);

    // XXX: double check conventions for possible path/interface/method names
    let message = Message::new_method_call(
        "io.github.Faithlife_Community.OuDedetai",
        "/io/github/Faithlife_Community/OuDedetai",
        "io.github.Faithlife_Community.OuDedetai.FaithLifeApp",
        "Launch",
    );
    if let Err(error) = &message {
        eprintln!("Failed to print to dbus: {}", error);
    };
    let message = message.unwrap();
    let message = message.append1(arguments);

    let result = c.send_with_reply_and_block(message, TIMEOUT);

    if let Err(error) = &result {
        eprintln!("Failed to send message over dbus: {}", error);
    }
}
